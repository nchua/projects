"""``book bakeoff``: compare image providers on fixture sheets (SPEC §8.3).

Flow (each step its own CLI call, so nothing expensive happens by accident):

1. **Plan** (default): providers × scenes × aspects × candidates from
   ``examples/bakeoff/scenes.yaml``, checked against the sheets on disk, with a
   list-price estimate. Nothing is called.
2. **Execute** (``--execute``): renders each scene through S7's ``render_prompt`` /
   ``select_references`` (so the bake-off tests what production sends), calls the
   provider, and appends to ``<out>/results.jsonl``. Resumable: jobs already in the
   file are skipped. Refusals are results (§7.5 policy test). A hard cap from
   ``BOOKGEN_MAX_IMAGE_COST_USD`` (default $150, [OPEN-11]) stops the run.
   Also writes ``<out>/human_scores.csv`` for the owner to fill in.
3. **Judge** (``--judge OUT``): Sonnet vision scores each image (identity, style,
   brief, no text, safe) against the sheets; scores go to ``<out>/judged.jsonl``.
4. **Report** (``--report OUT``): ``docs/bakeoff-<date>.md`` with per-provider
   refusal rate, latency, cost, judge means and any human scores.
5. **Pin** (``--pin PROVIDER --series ID --out RUN``): writes the provider and the
   model it used in that run into the series' ``style.json`` (D5); refuses to change
   an existing pin.

Judging is billed as Claude calls under ``BOOKGEN_MAX_COST_USD`` (per invocation,
default $5), separate from the image cap; a full 360-image judge pass may take a few
resumed ``--judge`` invocations (already-judged images are skipped).
"""

from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import Field

from bookgen.craft import PROJECT_ROOT, load_style_bible_raw
from bookgen.io import read_model, write_model
from bookgen.models import (
    AppearanceCard,
    CastMember,
    FamilyProfile,
    IllustrationBrief,
    Model,
    Score,
    StageId,
    StyleBible,
)
from bookgen.paths import SeriesPaths
from bookgen.prompts import load_prompt
from bookgen.providers.images import ImageProvider, ImageProviderError, ImageResult
from bookgen.providers.llm import LLMProvider, Role
from bookgen.stages.base import StageInputError
from bookgen.stages.common import as_json
from bookgen.stages.s07_generate import (
    prompt_hash,
    render_prompt,
    select_references,
    style_text,
)

DEFAULT_SCENES = PROJECT_ROOT / "examples" / "bakeoff" / "scenes.yaml"
DEFAULT_OUT = PROJECT_ROOT / "bakeoff"


class BakeoffError(StageInputError):
    """Bad bake-off inputs (missing sheets, unknown scene file); exit code 2."""


class BudgetExceeded(RuntimeError):
    """The next job could push the run past ``BOOKGEN_MAX_IMAGE_COST_USD``."""


class Scene(Model):
    """One bake-off scene: an id and the brief S7 would render."""

    id: str = Field(description="Stable scene id, used in file names.")
    brief: IllustrationBrief = Field(description="The brief, exactly as S6 would write it.")


class BakeoffConfig(Model):
    """``scenes.yaml``."""

    style: str = Field(description="Style bible id from craft/style_bibles/.")
    family: Path = Field(description="Intake JSON with the appearance cards (project-relative).")
    aspects: list[str] = Field(min_length=1, description="Aspect ratios, e.g. 2:1 and 1:1.")
    candidates: int = Field(ge=1, description="Candidates per scene × aspect (§8.3: three).")
    cast: list[CastMember] = Field(description="Names and descriptions for the prompt.")
    scenes: list[Scene] = Field(min_length=1, description="The scenes.")


class Job(Model):
    """One provider × scene × aspect call (yields ``candidates`` images)."""

    provider: str
    scene: str
    aspect: str

    @property
    def key(self) -> str:
        """Stable id, also the output file stem."""
        return f"{self.provider}/{self.scene}_{self.aspect.replace(':', 'x')}"


class JobRecord(Model):
    """One line of ``results.jsonl``."""

    job: Job
    prompt_hash: str
    references: list[str]
    images: list[ImageResult]
    error: str | None = None


class ImageScore(Model):
    """The vision judge's verdict on one candidate (structured output)."""

    identity: Score = Field(description="0-3: characters match their sheets (worst counts).")
    style: Score = Field(description="0-3: the locked style.")
    brief: Score = Field(description="0-3: scene, poses, shot and text area match.")
    no_text: bool = Field(description="No letters, numbers, signs or writing anywhere.")
    safe: bool = Field(description="Nothing frightening or inappropriate for ages 4-6.")
    notes: str = Field(description="What is wrong, specifically; empty if nothing.")


class JudgedImage(Model):
    """One line of ``judged.jsonl``."""

    path: str
    provider: str
    scene: str
    score: ImageScore


def load_config(path: Path = DEFAULT_SCENES) -> BakeoffConfig:
    """Read and validate ``scenes.yaml``."""
    if not path.exists():
        raise BakeoffError(f"no scene file at {path}")
    return BakeoffConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def sheet_dirs(sheets: Path, config: BakeoffConfig) -> dict[str, Path]:
    """Folder per character id; raises listing every character with no sheet or crops."""
    needed = sorted({c.id for s in config.scenes for c in s.brief.characters})
    missing = [
        cid
        for cid in needed
        if not (sheets / cid / "sheet.png").exists()
        and not any((sheets / cid / "sheet_crops").glob("*.png"))
    ]
    if missing:
        raise BakeoffError(f"no sheet for {missing} under {sheets} (see examples/sheets/README.md)")
    return {cid: sheets / cid for cid in needed}


def plan_jobs(
    providers: Iterable[str], config: BakeoffConfig, limit: int | None = None
) -> list[Job]:
    """Every provider × scene × aspect, optionally only the first ``limit`` scenes."""
    scenes = config.scenes[:limit] if limit else config.scenes
    return [
        Job(provider=p, scene=s.id, aspect=a)
        for p in providers
        for s in scenes
        for a in config.aspects
    ]


def estimate(
    jobs: list[Job], providers: dict[str, ImageProvider], candidates: int
) -> dict[str, float]:
    """List-price estimate per provider, in USD [VERIFY-4]."""
    out: dict[str, float] = defaultdict(float)
    for j in jobs:
        out[j.provider] += providers[j.provider].capabilities().usd_per_image * candidates
    return dict(out)


def image_cap_usd() -> float:
    """``BOOKGEN_MAX_IMAGE_COST_USD`` (default $150, [OPEN-11])."""
    raw = os.environ.get("BOOKGEN_MAX_IMAGE_COST_USD", "150")
    try:
        return float(raw)
    except ValueError as exc:
        raise BakeoffError(f"BOOKGEN_MAX_IMAGE_COST_USD must be a number, got {raw!r}") from exc


def read_records(out: Path) -> list[JobRecord]:
    """Every record in ``<out>/results.jsonl``, retries included (empty if none yet)."""
    path = out / "results.jsonl"
    if not path.exists():
        return []
    return [JobRecord.model_validate_json(ln) for ln in path.read_text().splitlines() if ln.strip()]


def latest_records(out: Path) -> list[JobRecord]:
    """The last attempt per job: what the judge and report score."""
    return list({r.job.key: r for r in read_records(out)}.values())


def spent_usd(out: Path) -> float:
    """Everything paid for so far, failed and superseded attempts included."""
    return sum(i.cost_usd for r in read_records(out) for i in r.images)


def job_seed(job: Job) -> int:
    """A stable per-job seed, so seeded providers (FLUX) can replay a candidate."""
    return int(hashlib.sha256(job.key.encode()).hexdigest()[:8], 16) % 2**31


def execute(
    jobs: list[Job],
    config: BakeoffConfig,
    sheets: Path,
    out: Path,
    providers: dict[str, ImageProvider],
    cap_usd: float | None = None,
    log: Callable[[str], None] = lambda line: None,
) -> list[JobRecord]:
    """Run every job without a successful record; returns this call's new records.

    A job whose last attempt errored is retried. Candidates finished before an error are
    kept on the record and counted as spend. Raises ``BudgetExceeded`` before a job whose
    list-price worst case would pass the cap.
    """
    cap = image_cap_usd() if cap_usd is None else cap_usd
    dirs = sheet_dirs(sheets, config)
    anchors = sorted((sheets / "anchors").glob("*.png"))
    style = StyleBible.model_validate(load_style_bible_raw(config.style))
    cast = {c.id: c for c in config.cast}
    family = read_model(PROJECT_ROOT / config.family, FamilyProfile)
    cards: dict[str, AppearanceCard] = {c.person_id: c for c in family.appearance_cards}
    scenes = {s.id: s for s in config.scenes}
    done = {r.job.key for r in latest_records(out) if r.error is None}
    spent = spent_usd(out)
    new: list[JobRecord] = []
    out.mkdir(parents=True, exist_ok=True)
    for job in jobs:
        if job.key in done:
            continue
        provider = providers[job.provider]
        worst = provider.capabilities().usd_per_image * config.candidates
        if spent + worst > cap:
            raise BudgetExceeded(f"spent ${spent:.2f}; next job up to ${worst:.2f}; cap ${cap:.2f}")
        brief = scenes[job.scene].brief
        prompt = render_prompt(brief, style, cast, cards)
        refs = select_references(brief, dirs, anchors, provider.capabilities().max_references)
        record = JobRecord(
            job=job,
            prompt_hash=prompt_hash(prompt, refs),
            references=[str(r) for r in refs],
            images=[],
        )
        try:
            record.images = provider.generate(
                prompt, refs, job.aspect, config.candidates, job_seed(job), out / job.key
            )
        except ImageProviderError as exc:
            record.images, record.error = exc.partial, str(exc)
        spent += sum(i.cost_usd for i in record.images)
        with (out / "results.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")
        refused = sum(i.refused for i in record.images)
        err = f", ERROR {record.error}" if record.error else ""
        log(f"{job.key}: {len(record.images)} images, {refused} refused, ${spent:.2f} total{err}")
        new.append(record)
    write_human_sheet(out)
    return new


def write_human_sheet(out: Path) -> Path:
    """``human_scores.csv``: one row per image; keeps scores already typed in."""
    path = out / "human_scores.csv"
    fields = ["path", "provider", "scene", "identity", "style", "brief", "no_text", "notes"]
    kept = {row["path"]: row for row in _read_csv(path)}
    rows = []
    for r in latest_records(out):
        for img in r.images:
            if img.path is not None:
                key = str(img.path)
                rows.append(
                    kept.get(key) or {"path": key, "provider": r.job.provider, "scene": r.job.scene}
                )
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Rows of a CSV file, or none if it doesn't exist."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def judge(out: Path, config: BakeoffConfig, sheets: Path, llm: LLMProvider) -> list[JudgedImage]:
    """Score every unjudged image with the vision judge; appends to ``judged.jsonl``."""
    path = out / "judged.jsonl"
    already = {
        JudgedImage.model_validate_json(ln).path
        for ln in (path.read_text().splitlines() if path.exists() else [])
        if ln
    }
    dirs = sheet_dirs(sheets, config)
    style = StyleBible.model_validate(load_style_bible_raw(config.style))
    scenes = {s.id: s for s in config.scenes}
    prompt = load_prompt("image_judge")
    session = llm.session(StageId.S8, out / "logs")
    new = []
    for record in latest_records(out):
        brief = scenes[record.job.scene].brief
        sheet_refs = select_references(brief, dirs, [], max_refs=len(brief.characters))
        for img in record.images:
            if img.path is None or str(img.path) in already:
                continue
            score = session.structured(
                role=Role.JUDGE,
                label=f"judge-{record.job.scene}",
                prompt=prompt,
                context=[],
                user=prompt.render(
                    style=style_text(style),
                    characters=", ".join(c.id for c in brief.characters) or "none",
                    brief=as_json(brief),
                ),
                schema=ImageScore,
                images=[*sheet_refs, img.path],
            )
            judged = JudgedImage(
                path=str(img.path),
                provider=record.job.provider,
                scene=record.job.scene,
                score=score,
            )
            with path.open("a", encoding="utf-8") as fh:
                fh.write(judged.model_dump_json() + "\n")
            new.append(judged)
    return new


def report(out: Path, docs: Path | None = None, today: str | None = None) -> Path:
    """Write ``docs/bakeoff-<date>.md`` from the results, judge scores and human sheet."""
    records = latest_records(out)
    if not records:
        raise BakeoffError(f"no results in {out}; run with --execute first")
    judged_path = out / "judged.jsonl"
    judged = [
        JudgedImage.model_validate_json(ln)
        for ln in (judged_path.read_text().splitlines() if judged_path.exists() else [])
        if ln
    ]
    human = _read_csv(out / "human_scores.csv")
    today = today or datetime.now(UTC).date().isoformat()
    lines = [
        f"# Image provider bake-off, {today}",
        "",
        f"Results: `{out}`. Protocol: SPEC §8.3. Generated by `book bakeoff --report`; "
        "the owner's pick and reasoning go at the end.",
        "",
        "| Provider | Model | Aspects sent | Jobs | Images | Refused | Errors | Latency/image (s) "
        "| Cost (USD) | Identity | Style | Brief | No text | Safe "
        "| Human identity | Human style | Human brief | Human no text |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    paid: dict[str, float] = defaultdict(float)
    for r in read_records(out):  # every attempt, so retried failures still count
        paid[r.job.provider] += sum(i.cost_usd for i in r.images)
    by_provider: dict[str, list[JobRecord]] = defaultdict(list)
    for r in records:
        by_provider[r.job.provider].append(r)
    for name, recs in sorted(by_provider.items()):
        imgs = [i for r in recs for i in r.images]
        made = [i for i in imgs if not i.refused]
        scores = [j.score for j in judged if j.provider == name]
        hum = [r for r in human if r["provider"] == name]
        model = imgs[0].model if imgs else "?"
        aspects = ", ".join(sorted({i.aspect for i in imgs if i.aspect})) or "?"
        lines.append(
            f"| {name} | {model} | {aspects} | {len(recs)} | {len(made)} | {len(imgs) - len(made)} "
            f"| {sum(r.error is not None for r in recs)} "
            f"| {_mean(i.latency_s for i in imgs):.1f} | {paid[name]:.2f} "
            f"| {_fmt(s.identity for s in scores)} | {_fmt(s.style for s in scores)} "
            f"| {_fmt(s.brief for s in scores)} | {_pct(s.no_text for s in scores)} "
            f"| {_pct(s.safe for s in scores)} | {_human(hum, 'identity')} "
            f"| {_human(hum, 'style')} | {_human(hum, 'brief')} | {_human_bool(hum, 'no_text')} |"
        )
    refusals = [
        f"- {r.job.key}: {i.refusal_reason or 'refused'}"
        for r in records
        for i in r.images
        if i.refused
    ]
    shown = refusals[:50]
    if len(refusals) > len(shown):
        shown.append(f"- … and {len(refusals) - len(shown)} more (see results.jsonl)")
    lines += ["", "## Refusals (child-hero policy test, §7.5)", "", *(shown or ["- none"])]
    lines += ["", "## Decision", "", "_Owner: provider picked, why, and the pin command run._", ""]
    docs = docs or PROJECT_ROOT / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / f"bakeoff-{today}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _mean(values: Iterable[float]) -> float:
    """Arithmetic mean, 0 for nothing."""
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def _fmt(values: Iterable[float]) -> str:
    """Mean to two places, or a dash when there are no scores."""
    vals = list(values)
    return f"{_mean(vals):.2f}" if vals else "–"


def _human(rows: list[dict[str, str]], column: str) -> str:
    """Mean of a human 0-3 score column over the rows that filled it in."""
    return _fmt(float(r[column]) for r in rows if r.get(column))


def _human_bool(rows: list[dict[str, str]], column: str) -> str:
    """Share of rows marking a yes/no column true (y, yes, true, 1)."""
    marks = [r[column].strip().lower() in {"y", "yes", "true", "1"} for r in rows if r.get(column)]
    return _pct(marks)


def _pct(values: Iterable[bool]) -> str:
    """Share true as a percentage, or a dash."""
    vals = list(values)
    return f"{100 * sum(vals) / len(vals):.0f}%" if vals else "–"


def models_in_run(out: Path) -> dict[str, str]:
    """Provider name to the model that actually made the images in a run."""
    return {i.provider: i.model for r in read_records(out) for i in r.images}


def pin(paths: SeriesPaths, provider: str, run: Path) -> StyleBible:
    """Pin ``provider`` with the model it used in ``run`` (D5); never a silent re-pin.

    The model comes from the run's records, not today's env default, so the pin is
    exactly what the bake-off tested.
    """
    if not paths.style.exists():
        raise BakeoffError(f"no style.json for series at {paths.root}; run init-series first")
    model = models_in_run(run).get(provider)
    if model is None:
        raise BakeoffError(f"{provider} made no images in {run}; nothing tested to pin")
    style = read_model(paths.style, StyleBible)
    if style.provider and (style.provider, style.model) != (provider, model):
        raise BakeoffError(
            f"series is pinned to {style.provider}/{style.model} (D5); "
            "edit style.json by hand to change it"
        )
    pinned = style.model_copy(
        update={"provider": provider, "model": model, "pinned_at": datetime.now(UTC)}
    )
    write_model(paths.style, pinned)
    return pinned


def stamp() -> str:
    """A UTC timestamp for a new run folder."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


__all__ = [
    "BakeoffConfig",
    "BakeoffError",
    "BudgetExceeded",
    "DEFAULT_OUT",
    "DEFAULT_SCENES",
    "estimate",
    "execute",
    "judge",
    "load_config",
    "pin",
    "plan_jobs",
    "report",
    "stamp",
]
