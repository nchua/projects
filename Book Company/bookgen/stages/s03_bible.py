"""S3 Series bible (SPEC §3.3 S3).

In:   profile, cards, companion, value priorities, parent notes. Episode 1 only.
Out:  `series/bible.json` (SeriesBible): world (name, 5-8 locations), cast, tone and humor
      register, naming conventions, the season (goal, six loglines, finale shape), forbidden list
      from parent exclusions, style id. Also `series/style_anchors/*.png`: 3-5 key locations in
      the chosen style.
Gate: coherence judge, human read (§3.2).

Session 2: bible.json only (style anchors are images, session 3). Code checks the
hard rules (exact names, cameo consent, ids, one home); the Sonnet judge checks
coherence (``craft/prompts/bible_judge.md``); the human read is always a flag
(``bible_human_read``) that the editor clears with ``book flags --resolve``.
Parent exclusions are merged into ``forbidden`` by code, not left to the model.
S3 also creates ``characters/<id>/`` for side cast, so S2 and S6 can find them.
"""

from __future__ import annotations

from pathlib import Path

from bookgen.craft import load_craft_guide
from bookgen.io import write_model
from bookgen.models import (
    CheckResult,
    FamilyProfile,
    Judgement,
    SeriesBible,
    SeriesBibleDraft,
    StageId,
)
from bookgen.prompts import load_prompt
from bookgen.providers.llm import Role
from bookgen.stages.base import Cadence, StageContext, StageResult
from bookgen.stages.common import (
    as_json,
    band_rule,
    companion_entry,
    judge_checks,
    load_profile,
    load_style,
    value_entry,
)

STAGE_ID = StageId.S3
CADENCE = Cadence.ONCE_PER_SERIES

JUDGE_CHECKS = (
    "names_exact",
    "forbidden_respected",
    "companion_true",
    "world_specific",
    "cast_distinct",
    "season_coherent",
    "tone_fits_band",
)
"""Codes the coherence judge must answer (mirrors ``craft/prompts/bible_judge.md``)."""


def inputs(ctx: StageContext) -> list[Path]:
    """S0's outputs: the profile and the locked style."""
    return [ctx.paths.profile, ctx.paths.style]


def outputs(ctx: StageContext) -> list[Path]:
    """``series/bible.json``."""
    return [ctx.paths.bible]


def _companion_brief(profile: FamilyProfile) -> str:
    """The archetype entry plus the child's name and colour for it."""
    choice = profile.companion_choice
    return as_json(
        {
            **companion_entry(profile).model_dump(),
            "id": profile.companion_id,
            "given_name": choice.name,
            "colour": choice.colour,
        }
    )


def _cameo_ids(profile: FamilyProfile) -> list[str]:
    """Parents and pets who may appear (consent.family_cameos)."""
    if not profile.consent.family_cameos:
        return []
    return [p.id for p in (*profile.parents, *profile.pets)]


def code_checks(bible: SeriesBible, profile: FamilyProfile) -> list[CheckResult]:
    """Hard rules the model must not get wrong; each a CheckResult."""
    cast = {c.id: c for c in bible.cast}
    hero = profile.hero
    problems: list[str] = []
    h = cast.get(hero.id)
    if h is None or h.name != hero.name or h.role != "hero" or h.pronouns != hero.pronouns:
        problems.append(f"hero must be id {hero.id!r}, name {hero.name!r}, {hero.pronouns}")
    comp = cast.get(profile.companion_id)
    if comp is None or comp.name != profile.companion_choice.name or comp.role != "companion":
        problems.append(
            f"companion must be {profile.companion_id!r} named {profile.companion_choice.name!r}"
        )
    may_appear = set(_cameo_ids(profile)) | {ch.id for ch in profile.children}
    family = {p.id: p for p in (*profile.parents, *profile.children, *profile.pets)}
    for c in bible.cast:
        if c.id in family and c.id not in may_appear:
            problems.append(f"{c.id} appears without cameo consent")
        person = family.get(c.id)
        if person is not None and c.name != person.name:
            problems.append(f"{c.id} is spelled {c.name!r}, profile says {person.name!r}")
        pronouns = getattr(person, "pronouns", None)
        if pronouns and c.pronouns != pronouns:
            problems.append(f"{c.id} pronouns {c.pronouns!r}, profile says {pronouns!r}")
    if len(cast) != len(bible.cast):
        problems.append("cast ids repeat")
    homes = [loc.name for loc in bible.world.locations if loc.is_home]
    names = [loc.name for loc in bible.world.locations]
    return [
        CheckResult(code="cast_matches_profile", passed=not problems, detail="; ".join(problems)),
        CheckResult(
            code="one_home", passed=len(homes) == 1, detail=f"home locations: {homes or 'none'}"
        ),
        CheckResult(
            code="locations_unique",
            passed=len(set(names)) == len(names),
            detail=f"{len(names)} locations",
        ),
    ]


def run(ctx: StageContext) -> StageResult:
    """Write the bible, then check it in code and with the coherence judge."""
    llm = ctx.need_llm()
    paths = ctx.paths
    profile = load_profile(paths)
    style = load_style(paths)
    values = [value_entry(v).model_dump() for v in profile.value_priorities]
    shared = {
        "profile": as_json(profile, exclude={"consent"}),
        "companion": _companion_brief(profile),
        "band": as_json(band_rule(profile)),
    }
    prompt, judge_prompt = load_prompt("bible"), load_prompt("bible_judge")
    draft = llm.structured(
        role=Role.WRITER,
        label="bible",
        prompt=prompt,
        context=[load_craft_guide()],
        user=prompt.render(
            **shared,
            values=as_json(values),
            cameos=", ".join(_cameo_ids(profile)) or "none",
            style=f"{style.id} ({style.name})",
            series_id=paths.root.name,
        ),
        schema=SeriesBibleDraft,
    )
    forbidden = list(dict.fromkeys([*profile.exclusions, *draft.forbidden]))
    bible = SeriesBible(
        **{**draft.model_dump(), "forbidden": forbidden},
        series_id=paths.root.name,
        style_id=style.id,
    )
    write_model(paths.bible, bible)
    for member in bible.cast:
        paths.character_dir(member.id).mkdir(parents=True, exist_ok=True)

    verdict = llm.structured(
        role=Role.JUDGE,
        label="bible-judge",
        prompt=judge_prompt,
        context=[load_craft_guide()],
        user=judge_prompt.render(**shared, bible=as_json(bible)),
        schema=Judgement,
    )
    checks = [
        *code_checks(bible, profile),
        *judge_checks(verdict, JUDGE_CHECKS),
        CheckResult(
            code="bible_human_read",
            passed=False,
            detail="Read series/bible.json; edit it if needed, then "
            "`book flags --series <id> --episode 1 --resolve <n>`.",
        ),
    ]
    return StageResult(checks=checks)
