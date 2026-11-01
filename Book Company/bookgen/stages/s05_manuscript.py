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

from bookgen.craft import load_rubric, manuscript_rubric_items
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
from bookgen.providers.llm import Role
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
    rule = load_rubric().pass_rule
    got = {s.key: s for s in critique.scores}
    checks, scores = [], []
    for item in manuscript_rubric_items():
        s = got.get(item.key)
        scores.append(s.score if s else 0)
        checks.append(
            CheckResult(
                code=f"rubric_{item.key}",
                passed=s is not None and s.score >= rule.min_item_score,
                detail=s.fix_notes if s else "unscored",
                value=s.score if s else None,
                kind="rubric",
            )
        )
    mean = sum(scores) / len(scores)
    checks.append(
        CheckResult(
            code="rubric_mean",
            passed=mean >= rule.min_mean,
            detail=f"judge mean {mean:.2f} (bar {rule.min_mean})",
            value=round(mean, 3),
            kind="rubric",
        )
    )
    return checks


def run(ctx: StageContext) -> StageResult:
    """Draft, critique and revise (at most twice), then gate on judge and mechanical checks."""
    llm = ctx.need_llm()
    paths = ctx.paths
    profile, bible, ledger = load_profile(paths), load_bible(paths), load_ledger(paths)
    plan = load_plan(paths, ctx.episode)
    context = writer_context(bible)
    writer, judge, reviser = load_prompt("writer"), load_prompt("critique"), load_prompt("revise")
    rubric_items = [i.model_dump(exclude={"applies_to"}) for i in manuscript_rubric_items()]
    shared = {  # every template takes what it needs; extra keys are ignored
        "names": names_sheet(profile, bible),
        "band": as_json(band_rule(profile)),
        "value": as_json(value_entry(plan.value)),
        "plan": as_json(plan),
        "ledger": as_json(ledger),
        "rubric": as_json(rubric_items),
    }
    draft = llm.structured(
        role=Role.WRITER,
        label="draft",
        prompt=writer,
        context=context,
        user=writer.render(**shared),
        schema=ManuscriptDraft,
        effort="high",
    )
    log = CritiqueLog(episode=ctx.episode)
    for rnd in range(MAX_REVISIONS + 1):
        mech, stats = check_manuscript(draft.spreads, plan, profile, bible)
        critique = llm.structured(
            role=Role.JUDGE,
            label=f"critique-{rnd}",
            prompt=judge,
            context=context,
            user=judge.render(**shared, manuscript=as_json(draft)),
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
            prompt=reviser,
            context=context,
            user=reviser.render(
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
        kind="metric",
    )
    return StageResult(checks=[*rubric, *mech, rounds])
