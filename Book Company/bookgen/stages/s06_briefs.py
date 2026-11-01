"""S6 Illustration briefs (SPEC §3.3 S6).

In:   manuscript, plan, bible, sheets, style bible.
Out:  `epNN/briefs.json` (IllustrationBrief per spread plus cover, recap and teaser): scene in
      concrete nouns, characters with pose and expression, shot, text-safe area, palette and time
      of day, continuity props, negatives.
Gate: lint, every present character has a sheet, text-safe side matches the plan.

Session 2: sheets don't exist until session 3, so "has a sheet" is checked as
"has ``characters/<id>/sheet.png`` or at least a ``characters/<id>/`` folder"
(S0 makes family and companion folders, S3 makes side-cast folders). Lint: all
fifteen slots exactly once, story-spread characters and text side match the plan,
no readable text requested in a scene, and "no text" among the negatives (D4).
"""

from __future__ import annotations

import re
from pathlib import Path

from bookgen.io import read_model, write_model
from bookgen.models import (
    Briefs,
    BriefsDraft,
    CheckResult,
    EpisodePlan,
    IllustrationBrief,
    Manuscript,
    StageId,
)
from bookgen.paths import SeriesPaths
from bookgen.prompts import load_prompt
from bookgen.providers.llm import Role
from bookgen.qa import none_of, per_spread
from bookgen.stages.base import Cadence, StageContext, StageResult
from bookgen.stages.common import (
    as_json,
    load_bible,
    load_ledger,
    load_plan,
    load_style,
    writer_context,
)

STAGE_ID = StageId.S6
CADENCE = Cadence.PER_EPISODE

SLOTS: list[int | str] = [*range(1, 13), "cover", "recap", "teaser"]
"""Every image a book needs (§3.3 S6)."""

TEXT_IN_ART_RE = re.compile(
    r"\b(sign(post)?s? (that )?(reads?|says?)|label(led|ed|s)? with|written|lettering|"
    r"words? on|reads? [\"'“])",
    re.IGNORECASE,
)
"""A scene asking for readable text in the art (D4: text is typeset, never painted)."""

NO_TEXT_RE = re.compile(r"\b(text|letter(ing|s)?|words?|signs?|labels?|writing)\b", re.IGNORECASE)
"""A negative that rules out text in the image."""


def inputs(ctx: StageContext) -> list[Path]:
    """Manuscript, plan, bible, style and ledger."""
    p = ctx.paths
    return [p.manuscript(ctx.episode), p.plan(ctx.episode), p.bible, p.style, p.ledger]


def outputs(ctx: StageContext) -> list[Path]:
    """``epNN/briefs.json``."""
    return [ctx.paths.briefs(ctx.episode)]


def has_sheet_or_folder(paths: SeriesPaths, person_id: str) -> bool:
    """Session 2 stand-in for "has a sheet": the sheet, or at least the character folder."""
    d = paths.character_dir(person_id)
    return (d / "sheet.png").exists() or d.is_dir()


def lint(
    briefs: list[IllustrationBrief], plan: EpisodePlan, paths: SeriesPaths
) -> list[CheckResult]:
    """The S6 gate: complete slots, sheets, plan agreement, no text in the art."""
    slots = [b.spread for b in briefs]
    missing = [s for s in SLOTS if s not in slots]
    dupes = sorted({str(s) for s in slots if slots.count(s) > 1})
    drawn_ids = {c.id for b in briefs for c in b.characters}
    beats = {b.spread: b for b in plan.beats}
    side_fail: dict[int | str, str] = {}
    cast_fail: dict[int | str, str] = {}
    text_fail: dict[int | str, str] = {}
    neg_fail: dict[int | str, str] = {}
    for b in briefs:
        if isinstance(b.spread, int):
            beat = beats[b.spread]
            if b.text_side != beat.text_side:
                side_fail[b.spread] = f"brief {b.text_side}, plan {beat.text_side}"
            drawn = {c.id for c in b.characters}
            if drawn != set(beat.characters):
                cast_fail[b.spread] = f"brief {sorted(drawn)}, plan {sorted(beat.characters)}"
        if TEXT_IN_ART_RE.search(b.scene):
            text_fail[b.spread] = f"{b.spread}: scene asks for readable text"
        if not any(NO_TEXT_RE.search(n) for n in b.negatives):
            neg_fail[b.spread] = f"{b.spread}: negatives don't rule out text"
    return [
        none_of("briefs_complete", [*missing, *dupes], "missing or duplicated slots"),
        none_of(
            "characters_have_sheets",
            sorted(i for i in drawn_ids if not has_sheet_or_folder(paths, i)),
            "no sheet or folder",
        ),
        *per_spread("text_side_matches_plan", side_fail),
        *per_spread("characters_match_plan", cast_fail),
        *per_spread("no_text_in_scene", text_fail),
        *per_spread("negatives_rule_out_text", neg_fail),
    ]


def run(ctx: StageContext) -> StageResult:
    """Write the fifteen briefs, then lint them against the plan and the character folders."""
    llm = ctx.need_llm()
    paths = ctx.paths
    plan = load_plan(paths, ctx.episode)
    manuscript = read_model(paths.manuscript(ctx.episode), Manuscript)
    prompt = load_prompt("briefs")
    draft = llm.structured(
        role=Role.WRITER,
        label="briefs",
        prompt=prompt,
        context=writer_context(load_bible(paths)),
        user=prompt.render(
            style=as_json(
                load_style(paths), exclude={"anchor_images", "provider", "model", "pinned_at"}
            ),
            ledger=as_json(load_ledger(paths)),
            plan=as_json(plan, exclude={"recap", "teaser", "grownup_questions"}),
            manuscript=as_json(manuscript, include={"spreads"}),
        ),
        schema=BriefsDraft,
    )
    briefs = Briefs(**draft.model_dump(), episode=ctx.episode)
    write_model(paths.briefs(ctx.episode), briefs)
    return StageResult(checks=lint(briefs.briefs, plan, paths))
