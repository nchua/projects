"""Minimal eval runner (SPEC §6.7): plan and manuscript stages over fixture families.

``book eval --suite evals/core`` reads ``suite.yaml`` (families × values). Per
family it runs S0 and S3 once (the bible doesn't depend on the value), copies
that series once per value and runs S4 and S5 there, all under
``<suite>/runs/<stamp>/`` (gitignored),
and writes ``<suite>/results/<stamp>.json`` (committed, so history is diffable).
It then prints deltas against the previous results file: judge mean, mechanical
failures, plan flags and cost. One provider is shared across the whole run, so
``BOOKGEN_MAX_COST_USD`` caps the eval as a whole; a case that fails is recorded
with its error and the run continues, except on the cost cap, which stops it.
"""

from __future__ import annotations

import dataclasses
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bookgen.craft import CRAFT_DIR, PROJECT_ROOT
from bookgen.io import read_model, write_model
from bookgen.manifest import read_manifest
from bookgen.models import StageId, Value
from bookgen.prompts import load_prompt
from bookgen.providers.llm import CostCapExceeded, LLMProvider
from bookgen.stages import run_range
from bookgen.stages.base import StageContext
from bookgen.stages.s00_intake import load_intake

CASE_STAGES = [StageId.S4, StageId.S5]
"""The plan and manuscript stages, run per family × value (§6.7)."""


class Suite(BaseModel):
    """``suite.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Suite name.")
    families: list[Path] = Field(min_length=1, description="Intake JSONs, project-relative.")
    values: list[Value] = Field(min_length=1, description="Values to run for each family.")


class EvalCase(BaseModel):
    """One family × value result."""

    family: str
    value: Value
    judge_scores: dict[str, float] = Field(default_factory=dict)
    judge_mean: float | None = None
    judge_rounds: int | None = None
    mechanical_failures: list[str] = Field(default_factory=list)
    plan_flags: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    error: str | None = None


class EvalRun(BaseModel):
    """``results/<stamp>.json``."""

    suite: str
    stamp: str
    prompts: dict[str, str] = Field(description="Prompt name to 'v<version>-<sha>'.")
    bible_cost_usd: dict[str, float] = Field(
        default_factory=dict, description="Family id to its one S3 run's cost."
    )
    cases: list[EvalCase]

    @property
    def judge_mean(self) -> float | None:
        """Mean of case judge means, over cases that produced one."""
        means = [c.judge_mean for c in self.cases if c.judge_mean is not None]
        return sum(means) / len(means) if means else None

    @property
    def mechanical_failures(self) -> int:
        """Total failing mechanical checks."""
        return sum(len(c.mechanical_failures) for c in self.cases)

    @property
    def plan_flags(self) -> int:
        """Total plan flags."""
        return sum(len(c.plan_flags) for c in self.cases)

    @property
    def cost_usd(self) -> float:
        """Total cost: every case plus each family's bible."""
        return sum(c.cost_usd for c in self.cases) + sum(self.bible_cost_usd.values())


def load_suite(suite_dir: Path) -> Suite:
    """Read ``<suite_dir>/suite.yaml``."""
    return Suite.model_validate(yaml.safe_load((suite_dir / "suite.yaml").read_text()))


def prompt_versions() -> dict[str, str]:
    """Every prompt file's version and sha, so a result names the text that made it."""
    names = sorted(p.stem for p in (CRAFT_DIR / "prompts").glob("*.md") if p.stem != "README")
    return {n: f"v{load_prompt(n).version}-{load_prompt(n).sha}" for n in names}


def _collect(ctx: StageContext, case: EvalCase) -> EvalCase:
    """Read one case's S4/S5 scores, failures, flags and cost from its manifest."""
    m = read_manifest(ctx.paths.manifest(1), 1)
    case.cost_usd = round(sum(m.stages[s].cost_usd for s in CASE_STAGES if s in m.stages), 6)
    if (s4 := m.stages.get(StageId.S4)) is not None:
        case.plan_flags = [c.code for c in s4.checks if not c.passed]
    if (s5 := m.stages.get(StageId.S5)) is not None:
        for c in s5.checks:
            if c.kind == "rubric" and c.code == "rubric_mean":
                case.judge_mean = c.value
            elif c.kind == "rubric" and c.value is not None:
                case.judge_scores[c.code.removeprefix("rubric_")] = c.value
            elif c.kind == "metric" and c.code == "judge_rounds":
                case.judge_rounds = int(c.value or 0)
            elif c.kind == "check" and not c.passed:
                case.mechanical_failures.append(c.code)
    return case


def run_suite(
    suite_dir: Path, llm: LLMProvider, stamp: str | None = None
) -> tuple[EvalRun, EvalRun | None]:
    """Run every case; write results; return ``(this run, previous run or None)``."""
    suite = load_suite(suite_dir)
    stamp = stamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results_dir = suite_dir / "results"
    previous = latest_results(results_dir)
    base = suite_dir / "runs" / stamp
    run = EvalRun(suite=suite.name, stamp=stamp, prompts=prompt_versions(), cases=[])
    try:
        for family_path in suite.families:
            _run_family(PROJECT_ROOT / family_path, suite.values, base, llm, run)
    except CostCapExceeded:
        pass  # recorded on the case that hit it; the cap stops the whole suite
    write_model(results_dir / f"{stamp}.json", run)
    return run, previous


def _run_family(
    family_file: Path, values: list[Value], base: Path, llm: LLMProvider, run: EvalRun
) -> None:
    """S0 and S3 once for the family, then S4-S5 per value in a copy of that series.

    Appends one case per value to ``run``; ``CostCapExceeded`` propagates (after the
    case that hit it is recorded) and stops the suite.
    """
    family = StageContext(family_path=family_file, base_dir=base)
    family = dataclasses.replace(family, series_id=load_intake(family).id)
    bible_error: str | None = None
    try:
        run_range(family, [StageId.S0])
        run_range(family, [StageId.S3], llm=llm)
    except CostCapExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 - every case of this family records it
        bible_error = f"S3 {type(exc).__name__}: {exc}"
    s3 = read_manifest(family.paths.manifest(1), 1).stages.get(StageId.S3)
    run.bible_cost_usd[str(family.series_id)] = round(s3.cost_usd, 6) if s3 else 0.0
    for value in values:
        case = EvalCase(family=str(family.series_id), value=value, error=bible_error)
        if bible_error is not None:
            run.cases.append(case)
            continue
        ctx = dataclasses.replace(family, series_id=f"{family.series_id}-{value}", value=value)
        shutil.copytree(family.paths.root, ctx.paths.root)
        try:
            run_range(ctx, CASE_STAGES, llm=llm)
        except CostCapExceeded as exc:
            case.error = str(exc)
            run.cases.append(_collect(ctx, case))
            raise
        except Exception as exc:  # noqa: BLE001 - record and carry on with the suite
            case.error = f"{type(exc).__name__}: {exc}"
        run.cases.append(_collect(ctx, case))


def latest_results(results_dir: Path) -> EvalRun | None:
    """The most recent results file, if any."""
    files = sorted(results_dir.glob("*.json"))
    return read_model(files[-1], EvalRun) if files else None


def report(run: EvalRun, previous: EvalRun | None) -> list[str]:
    """Human-readable lines: per-case scores, then totals with deltas vs ``previous``."""

    def delta(now: float | None, before: float | None, fmt: str) -> str:
        """``now`` formatted, with the signed change from ``before`` when there is one."""
        if now is None:
            return "n/a"
        if before is None:
            return format(now, fmt)
        return f"{now:{fmt}} ({now - before:+{fmt}})"

    lines = [f"suite {run.suite} @ {run.stamp}"]
    for c in run.cases:
        mean = f"{c.judge_mean:.2f}" if c.judge_mean is not None else "n/a"
        err = f"  ERROR {c.error}" if c.error else ""
        lines.append(
            f"  {c.family}/{c.value}: judge {mean}, mech fails {len(c.mechanical_failures)}, "
            f"plan flags {len(c.plan_flags)}, ${c.cost_usd:.3f}{err}"
        )
    p = previous
    totals = [
        ("judge mean", run.judge_mean, p.judge_mean if p else None, ".2f"),
        ("mechanical failures", run.mechanical_failures, p.mechanical_failures if p else None, "d"),
        ("plan flags", run.plan_flags, p.plan_flags if p else None, "d"),
        ("cost USD", run.cost_usd, p.cost_usd if p else None, ".3f"),
    ]
    lines += [f"{name + ':':<21}{delta(now, before, fmt)}" for name, now, before, fmt in totals]
    if p:
        changed = sorted(k for k in run.prompts if run.prompts[k] != p.prompts.get(k))
        lines.append(f"prompts changed since {p.stamp}: {changed or 'none'}")
    return lines
