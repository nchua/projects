"""S4 Episode plan (SPEC §3.3 S4).

In:   bible, ledger, this episode's value, life-event note, band.
Out:  `epNN/plan.json` (EpisodePlan): title, logline, value and pattern, structure template,
      12 beats (spread, setting, characters, action, emotion, hook, text-safe side), the beat
      where the value lands (9-11), recap, teaser, three grown-up questions.
Gate: the plan judge checks 12 beats, pattern present, continuity against the ledger, no
      setting repeated from the previous episode, scare level within band, and that the story
      reads without the recap (§4.5).

Session 2: code checks the countable rules (pattern copied from the catalog, value lands
9-11, value not repeated this season, recap <= 60 words, ledger summary <= 120, known cast
and settings, no non-home setting repeated from the previous episode, template rotation);
the Sonnet plan judge (``craft/prompts/plan_judge.md``) reads the plan with the recap
removed and checks continuity, scare level, standalone, pattern enacted, value lands.
With no ``--value``, the first parent priority not yet covered in the ledger is used.
"""

from __future__ import annotations

from pathlib import Path

from bookgen.io import write_model
from bookgen.models import (
    CheckResult,
    EpisodePlan,
    FamilyProfile,
    Judgement,
    Ledger,
    SeriesBible,
    StageId,
    Value,
)
from bookgen.prompts import load_prompt
from bookgen.providers.llm import Role
from bookgen.qa.limits import LEDGER_SUMMARY_MAX_WORDS, RECAP_MAX_WORDS, max_words
from bookgen.stages.base import Cadence, StageContext, StageInputError, StageResult
from bookgen.stages.common import (
    as_json,
    band_rule,
    judge_checks,
    load_bible,
    load_ledger,
    load_profile,
    previous_plan,
    template_entries,
    value_entry,
    writer_context,
)

STAGE_ID = StageId.S4
CADENCE = Cadence.PER_EPISODE

JUDGE_CHECKS = {
    "continuity": "no contradiction with ledger or bible",
    "scare_level": "within band; mild scares resolve in two spreads",
    "standalone": "followable without the recap",
    "pattern_enacted": "beats enact the value pattern, shown not told",
    "value_lands": "the turn is the hero's costly choice at the claimed spread",
}
"""Codes the plan judge must answer (mirrors ``craft/prompts/plan_judge.md``)."""


def inputs(ctx: StageContext) -> list[Path]:
    """Profile, bible and ledger."""
    return [ctx.paths.profile, ctx.paths.bible, ctx.paths.ledger]


def outputs(ctx: StageContext) -> list[Path]:
    """``epNN/plan.json``."""
    return [ctx.paths.plan(ctx.episode)]


def choose_value(ctx: StageContext, profile: FamilyProfile, ledger: Ledger) -> Value:
    """``--value``, else the first parent priority not yet covered this season."""
    if ctx.value is not None:
        return ctx.value
    covered = {lc.value for lc in ledger.lessons_covered}
    for v in profile.value_priorities:
        if v not in covered:
            return v
    raise StageInputError("every priority value is covered; pass --value")


def check(ctx: StageContext) -> None:
    """A value can be chosen (pure)."""
    choose_value(ctx, load_profile(ctx.paths), load_ledger(ctx.paths))


def code_checks(
    plan: EpisodePlan, bible: SeriesBible, ledger: Ledger, prev: EpisodePlan | None
) -> list[CheckResult]:
    """The countable §3.3 S4 / §4.4 / §4.5 rules, each a CheckResult."""
    entry = value_entry(plan.value)
    cast = {c.id for c in bible.cast}
    places = {loc.name for loc in bible.world.locations}
    homes = {loc.name for loc in bible.world.locations if loc.is_home}
    unknown_chars = sorted({c for b in plan.beats for c in b.characters} - cast)
    unknown_places = sorted({b.setting for b in plan.beats} - places)
    away = {b.setting for b in plan.beats} - homes
    repeated = sorted(away & ({b.setting for b in prev.beats} - homes)) if prev else []
    covered = {lc.value for lc in ledger.lessons_covered}
    return [
        CheckResult(code="beats_12", passed=len(plan.beats) == 12, value=len(plan.beats)),
        CheckResult(
            code="pattern_present",
            passed=plan.pattern == entry.pattern,
            detail=f"plan {plan.pattern} vs catalog {entry.pattern}",
        ),
        CheckResult(
            code="value_lands_9_11",
            passed=9 <= plan.value_lands_at <= 11,
            detail=f"value lands at spread {plan.value_lands_at}",
            value=plan.value_lands_at,
        ),
        CheckResult(
            code="value_not_repeated",
            passed=plan.value not in covered,
            detail=f"{plan.value} already covered this season" if plan.value in covered else "",
        ),
        max_words("recap_length", plan.recap, RECAP_MAX_WORDS, "recap"),
        max_words(
            "ledger_summary_length", ledger.last_summary, LEDGER_SUMMARY_MAX_WORDS, "ledger summary"
        ),
        CheckResult(
            code="cast_known",
            passed=not unknown_chars,
            detail=f"not in the bible cast: {unknown_chars}" if unknown_chars else "",
        ),
        CheckResult(
            code="settings_known",
            passed=not unknown_places,
            detail=f"not bible locations: {unknown_places}" if unknown_places else "",
        ),
        CheckResult(
            code="setting_not_repeated",
            passed=not repeated,
            detail=f"repeated from the previous episode: {repeated}" if repeated else "",
        ),
        CheckResult(
            code="template_rotates",
            passed=prev is None or plan.template != prev.template,
            detail=f"template {plan.template}" + (f", previous {prev.template}" if prev else ""),
        ),
    ]


def _previous_summary(prev: EpisodePlan | None) -> str:
    """Title, template and settings of the previous episode, or ``none``."""
    if prev is None:
        return "none"
    settings = sorted({b.setting for b in prev.beats})
    return as_json({"title": prev.title, "template": prev.template, "settings": settings})


def run(ctx: StageContext) -> StageResult:
    """Plan the episode, then check it in code and with the plan judge."""
    llm = ctx.need_llm()
    paths = ctx.paths
    profile, bible, ledger = load_profile(paths), load_bible(paths), load_ledger(paths)
    prev = previous_plan(paths, ctx.episode)
    value = choose_value(ctx, profile, ledger)
    templates = [t.model_dump() for t in template_entries() if not prev or t.id != prev.template]
    shared = {
        "value": as_json(value_entry(value)),
        "band": as_json(band_rule(profile)),
        "ledger": as_json(ledger),
    }
    context = writer_context(paths)
    draft = llm.structured(
        role=Role.WRITER,
        label="plan",
        prompt=load_prompt("plan"),
        context=context,
        user=load_prompt("plan").render(
            **shared,
            episode=str(ctx.episode),
            templates=as_json(templates),
            previous=_previous_summary(prev),
        ),
        schema=EpisodePlan,
    )
    plan = draft.model_copy(update={"episode": ctx.episode, "value": value})
    write_model(paths.plan(ctx.episode), plan)

    verdict = llm.structured(
        role=Role.JUDGE,
        label="plan-judge",
        prompt=load_prompt("plan_judge"),
        context=context,
        user=load_prompt("plan_judge").render(**shared, plan=as_json(plan, exclude={"recap"})),
        schema=Judgement,
    )
    checks = [
        *code_checks(plan, bible, ledger, prev),
        *judge_checks(verdict, JUDGE_CHECKS, prefix="judge_"),
    ]
    return StageResult(checks=checks)
