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

from bookgen.craft import load_templates
from bookgen.io import write_model
from bookgen.models import (
    CheckResult,
    EpisodePlan,
    EpisodePlanDraft,
    FamilyProfile,
    Judgement,
    Ledger,
    SeriesBible,
    StageId,
    Value,
)
from bookgen.prompts import load_prompt
from bookgen.providers.llm import Role
from bookgen.qa import none_of
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
    value_entry,
    writer_context,
)

STAGE_ID = StageId.S4
CADENCE = Cadence.PER_EPISODE

JUDGE_CHECKS = ("continuity", "scare_level", "standalone", "pattern_enacted", "value_lands")
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
    covered = {lc.value for lc in ledger.lessons_covered if lc.episode != plan.episode}
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
        none_of("value_not_repeated", [plan.value] if plan.value in covered else [], "covered"),
        max_words("recap_length", plan.recap, RECAP_MAX_WORDS, "recap"),
        max_words(
            "ledger_summary_length", ledger.last_summary, LEDGER_SUMMARY_MAX_WORDS, "ledger summary"
        ),
        none_of("cast_known", unknown_chars, "not in the bible cast"),
        none_of("settings_known", unknown_places, "not bible locations"),
        none_of("setting_not_repeated", repeated, "repeated from the previous episode"),
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
    templates = [t.model_dump() for t in load_templates() if not prev or t.id != prev.template]
    shared = {
        "value": as_json(value_entry(value)),
        "band": as_json(band_rule(profile)),
        "ledger": as_json(ledger),
    }
    context = writer_context(bible)
    prompt, judge_prompt = load_prompt("plan"), load_prompt("plan_judge")
    draft = llm.structured(
        role=Role.WRITER,
        label="plan",
        prompt=prompt,
        context=context,
        user=prompt.render(
            **shared,
            episode=str(ctx.episode),
            templates=as_json(templates),
            previous=_previous_summary(prev),
        ),
        schema=EpisodePlanDraft,
    )
    plan = EpisodePlan(**draft.model_dump(), episode=ctx.episode, value=value)
    write_model(paths.plan(ctx.episode), plan)

    verdict = llm.structured(
        role=Role.JUDGE,
        label="plan-judge",
        prompt=judge_prompt,
        context=context,
        user=judge_prompt.render(
            **{**shared, "ledger": as_json(ledger, exclude={"last_summary"})},
            plan=as_json(plan, exclude={"recap"}),
        ),
        schema=Judgement,
    )
    checks = [
        *code_checks(plan, bible, ledger, prev),
        *judge_checks(verdict, JUDGE_CHECKS),
    ]
    return StageResult(checks=checks)
