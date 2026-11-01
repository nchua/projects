"""S5 Manuscript (SPEC §3.3 S5).

In:   plan, Craft Guide, band rules, ledger (names, voices).
Out:  `epNN/manuscript.json` (Manuscript): text per spread plus read-aloud notes. Loop: writer
      drafts -> judge critiques against the rubric in a separate call -> writer revises -> at most
      two rounds -> mechanical checks (word counts per band, banned phrases, readability, exact
      name spellings, pronouns).
Gate: judge >= bar and mechanical checks pass, else flag.

Session 2: the loop is draft -> critique -> (revise -> critique) at most twice
(``MAX_REVISIONS``), so the final text always has a judge score to gate on. The
judge (Sonnet, ``craft/prompts/critique.md``) sees only the finished text, never
the writer's reasoning (§6.2). Failed mechanical checks (``bookgen/qa/mechanical``)
go to each revise along with the judge's notes. The loop stops early once the
rubric bar and every mechanical check pass. Every round is kept in
``epNN/critique.json``; the final scores and checks go to the manifest.
"""

from __future__ import annotations

from pathlib import Path

from bookgen.craft import load_rubric
from bookgen.io import write_model
from bookgen.models import (
    CheckResult,
    Critique,
    CritiqueLog,
    CritiqueRound,
    FamilyProfile,
    Manuscript,
    ManuscriptDraft,
    SeriesBible,
    StageId,
)
from bookgen.prompts import load_prompt
from bookgen.providers.llm import Role, StageLLM
from bookgen.qa.mechanical import check_manuscript, failed
from bookgen.stages.base import Cadence, StageContext, StageResult
from bookgen.stages.common import (
    as_json,
    band_rule,
    load_bible,
    load_ledger,
    load_plan,
    load_profile,
    value_entry,
    writer_context,
)

STAGE_ID = StageId.S5
CADENCE = Cadence.PER_EPISODE

MAX_REVISIONS = 2
"""§3.3 S5: at most two revise rounds after the first critique."""


def inputs(ctx: StageContext) -> list[Path]:
    """Plan, bible, ledger and profile."""
    p = ctx.paths
    return [p.plan(ctx.episode), p.bible, p.ledger, p.profile]


def outputs(ctx: StageContext) -> list[Path]:
    """``epNN/manuscript.json`` and ``epNN/critique.json``."""
    return [ctx.paths.manuscript(ctx.episode), ctx.paths.critique(ctx.episode)]


def names_sheet(profile: FamilyProfile, bible: SeriesBible) -> str:
    """Exact names, pronouns and parent terms for the writer and reviser."""
    return as_json(
        {
            "cast": [{"id": c.id, "name": c.name, "pronouns": c.pronouns} for c in bible.cast],
            "parents": [
                {"name": p.name, "child_calls_them": p.term, "pronouns": p.pronouns}
                for p in profile.parents
            ],
        }
    )


def rubric_gate(critique: Critique) -> list[CheckResult]:
    """One check per manuscript rubric item, plus the mean, under the §6.1 pass rule."""
    rubric = load_rubric()
    got = {s.key: s for s in critique.scores}
    checks, scores = [], []
    for item in (i for i in rubric.items if i.applies_to == "manuscript"):
        s = got.get(item.key)
        if s is None:
            checks.append(CheckResult(code=f"rubric_{item.key}", passed=False, detail="unscored"))
            scores.append(0)
            continue
        scores.append(s.score)
        checks.append(
            CheckResult(
                code=f"rubric_{item.key}",
                passed=s.score >= rubric.pass_rule.min_item_score,
                detail=s.fix_notes,
                value=s.score,
            )
        )
    mean = sum(scores) / len(scores)
    checks.append(
        CheckResult(
            code="rubric_mean",
            passed=mean >= rubric.pass_rule.min_mean,
            detail=f"judge mean {mean:.2f} (bar {rubric.pass_rule.min_mean})",
            value=round(mean, 3),
        )
    )
    return checks


def _rubric_items() -> str:
    """The manuscript rubric items, for the judge."""
    items = [i for i in load_rubric().items if i.applies_to == "manuscript"]
    return as_json([i.model_dump(exclude={"applies_to"}) for i in items])


def run(ctx: StageContext) -> StageResult:
    """Draft, critique and revise (at most twice), then gate on judge and mechanical checks."""
    llm: StageLLM = ctx.need_llm()
    paths = ctx.paths
    profile, bible, ledger = load_profile(paths), load_bible(paths), load_ledger(paths)
    plan = load_plan(paths, ctx.episode)
    context = writer_context(paths)
    shared = {
        "names": names_sheet(profile, bible),
        "band": as_json(band_rule(profile)),
        "value": as_json(value_entry(plan.value)),
        "plan": as_json(plan),
    }
    draft = llm.structured(
        role=Role.WRITER,
        label="draft",
        prompt=load_prompt("writer"),
        context=context,
        user=load_prompt("writer").render(**shared, ledger=as_json(ledger)),
        schema=ManuscriptDraft,
        effort="high",
    )
    log = CritiqueLog(episode=ctx.episode)
    for rnd in range(MAX_REVISIONS + 1):
        mech, stats = check_manuscript(draft.spreads, plan, profile, bible)
        critique = llm.structured(
            role=Role.JUDGE,
            label=f"critique-{rnd}",
            prompt=load_prompt("critique"),
            context=context,
            user=load_prompt("critique").render(
                rubric=_rubric_items(),
                value=shared["value"],
                band=shared["band"],
                ledger=as_json(ledger),
                plan=shared["plan"],
                manuscript=as_json(draft),
            ),
            schema=Critique,
        )
        log.rounds.append(
            CritiqueRound(round=rnd, critique=critique, mechanical_failures=failed(mech))
        )
        rubric = rubric_gate(critique)
        if rnd == MAX_REVISIONS or not failed([*rubric, *mech]):
            break
        draft = llm.structured(
            role=Role.WRITER,
            label=f"revise-{rnd + 1}",
            prompt=load_prompt("revise"),
            context=context,
            user=load_prompt("revise").render(
                **shared,
                manuscript=as_json(draft),
                critique=as_json(critique),
                failures=as_json([c.model_dump(exclude={"passed"}) for c in failed(mech)]),
            ),
            schema=ManuscriptDraft,
            effort="high",
        )
    manuscript = Manuscript(episode=ctx.episode, spreads=draft.spreads, stats=stats)
    write_model(paths.manuscript(ctx.episode), manuscript)
    write_model(paths.critique(ctx.episode), log)
    rounds = CheckResult(
        code="judge_rounds",
        passed=True,
        detail=f"{len(log.rounds)} judge round(s)",
        value=len(log.rounds),
    )
    return StageResult(checks=[*rubric, *mech, rounds])
