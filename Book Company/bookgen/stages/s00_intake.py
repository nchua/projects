"""S0 Intake (SPEC §3.3 S0).

In:   parent form (Phase 0: a hand-written profile, ``examples/family_demo.json``).
Out:  ``FamilyProfile`` with children, parents, pets, companion choice, value priorities,
      exclusions, locale, consent flags, written to ``family/profile.json``; the §3.4
      directory layout; ``series/style.json``; an empty ``series/ledger.json``; and an S0
      record in ``ep01/manifest.json``.
Gate: schema valid, consent flags set (§3.2). Enforced before anything is written; a
      failure raises ``IntakeError`` (bad input, not a flag).

Phase 0 additions: hand-written L1 appearance cards in the intake move to
``characters/<id>/appearance.json``. Re-running is safe: inputs are rewritten,
the ledger and existing appearance cards (which the parent may have edited
at the S1 gate) are never overwritten, and changing a series' locked style is refused (D5).
"""

from __future__ import annotations

import dataclasses

from pydantic import ValidationError

from bookgen.craft import load_band_rules, load_style_bible
from bookgen.io import read_model, write_model
from bookgen.models import FamilyProfile, Ledger, StageId, StyleBible
from bookgen.paths import SeriesPaths
from bookgen.stages.base import Cadence, StageContext, StageInputError, StageResult

STAGE_ID = StageId.S0
CADENCE = Cadence.EVERY_RUN

DEFAULT_STYLE = "gouache-warm"
"""Phase 0's only launch style [OPEN-12]."""


class IntakeError(StageInputError):
    """The intake form is invalid or conflicts with an existing series."""


def load_intake(ctx: StageContext) -> FamilyProfile:
    """Read and validate the intake JSON, applying the ``--companion`` override."""
    if ctx.family_path is None:
        raise IntakeError("S0 needs a family file (--family); use `book init-series`")
    try:
        profile = read_model(ctx.family_path, FamilyProfile)
    except (OSError, ValidationError) as exc:
        raise IntakeError(f"invalid family file {ctx.family_path}: {exc}") from exc
    if ctx.companion is not None:
        choice = profile.companion_choice.model_copy(update={"archetype": ctx.companion})
        profile = profile.model_copy(update={"companion_choice": choice})
    return profile


def with_series_id(ctx: StageContext) -> StageContext:
    """Default ``series_id`` to the family id (``--series`` overrides it)."""
    if ctx.series_id is not None:
        return ctx
    return dataclasses.replace(ctx, series_id=load_intake(ctx).id)


def check_intake(profile: FamilyProfile) -> None:
    """The §3.2 gate beyond the schema: consent set, hero in a Phase 0 band."""
    if not profile.consent.personalized_story:
        raise IntakeError("consent.personalized_story is false; cannot make a personalized book")
    hero = profile.hero  # siblings are cameos [OPEN-4], so only the hero's band gates
    if not load_band_rules().bands[hero.band].phase0:
        raise IntakeError(f"{hero.id}: band {hero.band} is not built in Phase 0 (§1.2)")


def resolve_style(paths: SeriesPaths, style_id: str) -> StyleBible | None:
    """Return the style bible to write, or ``None`` to keep the locked one (D5).

    Raises ``IntakeError`` for an unknown style or an attempt to change a locked one.
    The existing file is kept because it may carry anchors and a pinned provider.
    """
    if paths.style.exists():
        current = read_model(paths.style, StyleBible)
        if current.id != style_id:
            raise IntakeError(f"series style is locked to {current.id!r} (D5); got {style_id!r}")
        return None
    try:
        return load_style_bible(style_id)
    except FileNotFoundError as exc:
        raise IntakeError(str(exc)) from exc


def check(ctx: StageContext) -> None:
    """Validate the intake, the consent gate and the style lock; writes nothing."""
    check_intake(load_intake(ctx))
    resolve_style(ctx.paths, ctx.style_id or DEFAULT_STYLE)


def run(ctx: StageContext) -> StageResult:
    """Lay out ``series/<series_id>/`` and write the S0 artifacts (``check`` has passed)."""
    profile = load_intake(ctx)
    paths = ctx.paths
    style = resolve_style(paths, ctx.style_id or DEFAULT_STYLE)
    for d in paths.dirs(profile.character_ids, episode=1):
        d.mkdir(parents=True, exist_ok=True)
    if style is not None:
        write_model(paths.style, style)
    write_model(paths.profile, profile, exclude={"appearance_cards"})
    for card in profile.appearance_cards:
        if not paths.appearance(card.person_id).exists():
            write_model(paths.appearance(card.person_id), card)
    if not paths.ledger.exists():
        write_model(paths.ledger, Ledger())
    return StageResult()
