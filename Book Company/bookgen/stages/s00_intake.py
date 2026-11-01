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

from pydantic import ValidationError

from bookgen.craft import load_band_rules, load_style_bible_raw
from bookgen.io import read_model, write_model
from bookgen.manifest import finish_stage, start_stage
from bookgen.models import FamilyProfile, Ledger, StageId, StageStatus, StyleBible
from bookgen.paths import SeriesPaths
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S0

DEFAULT_STYLE = "gouache-warm"
"""Phase 0's only launch style [OPEN-12]."""


class IntakeError(ValueError):
    """The intake form is invalid or conflicts with an existing series."""


def load_intake(ctx: StageContext) -> FamilyProfile:
    """Read and validate the intake JSON, applying the ``--companion`` override."""
    if ctx.family_path is None:
        raise IntakeError("S0 needs a family file (--family)")
    try:
        profile = read_model(ctx.family_path, FamilyProfile)
    except (OSError, ValidationError) as exc:
        raise IntakeError(f"invalid family file {ctx.family_path}: {exc}") from exc
    if ctx.companion is not None:
        choice = profile.companion_choice.model_copy(update={"archetype": ctx.companion})
        profile = profile.model_copy(update={"companion_choice": choice})
    return profile


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
        return StyleBible.model_validate(load_style_bible_raw(style_id))
    except FileNotFoundError as exc:
        raise IntakeError(str(exc)) from exc


def run(ctx: StageContext) -> SeriesPaths:
    """Validate the intake and lay out ``series/<series_id>/``; returns its paths."""
    profile = load_intake(ctx)
    check_intake(profile)
    series_id = ctx.series_id or profile.id
    paths = SeriesPaths.for_series(series_id, ctx.base_dir)
    style = resolve_style(paths, ctx.style_id or DEFAULT_STYLE)  # validate before writing
    manifest = paths.manifest(1)

    start_stage(manifest, 1, STAGE_ID)
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
    finish_stage(manifest, 1, STAGE_ID, StageStatus.DONE)
    return paths
