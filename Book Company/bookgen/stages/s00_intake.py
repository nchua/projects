"""S0 Intake (SPEC §3.3 S0).

In:   parent form (Phase 0: a hand-written profile, ``examples/family_demo.json``).
Out:  ``FamilyProfile`` with children, parents, pets, companion choice, value priorities,
      exclusions, locale, consent flags, written to ``family/profile.json``; the §3.4
      directory layout; ``series/style.json``; an empty ``series/ledger.json``; and an S0
      record in ``ep01/manifest.json``.
Gate: none stated in §3.3. Invalid intake raises ``IntakeError`` (bad input, not a gate).

Phase 0 additions: hand-written L1 appearance cards in the intake move to
``characters/<id>/appearance.json``. Re-running is safe: inputs are rewritten,
the ledger is never overwritten, and changing a series' locked style is refused (D5).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from bookgen.craft import load_band_rules, load_style_bible_raw
from bookgen.manifest import finish_stage, start_stage
from bookgen.models import FamilyProfile, Ledger, StageId, StageStatus, StyleBible
from bookgen.paths import SeriesPaths
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S0

DEFAULT_STYLE = "gouache-warm"
"""Phase 0's only launch style [OPEN-12]."""


class IntakeError(ValueError):
    """The intake form is invalid or conflicts with an existing series."""


def companion_id(profile: FamilyProfile) -> str:
    """Character id for the companion: its given name, slugged ('Toast' -> 'toast')."""
    return re.sub(r"[^a-z0-9]+", "_", profile.companion_choice.name.lower()).strip("_")


def character_ids(profile: FamilyProfile) -> list[str]:
    """Everyone who gets a ``characters/<id>/`` folder: children, companion, consented cameos."""
    ids = [c.id for c in profile.children] + [companion_id(profile)]
    if profile.consent.family_cameos:
        ids += [p.id for p in profile.parents] + [p.id for p in profile.pets]
    return ids


def load_intake(ctx: StageContext) -> FamilyProfile:
    """Read and validate the intake JSON, applying the ``--companion`` override."""
    if ctx.family_path is None:
        raise IntakeError("S0 needs a family file (--family)")
    try:
        profile = FamilyProfile.model_validate_json(ctx.family_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise IntakeError(f"invalid family file {ctx.family_path}: {exc}") from exc
    if ctx.companion is not None:
        choice = profile.companion_choice.model_copy(update={"archetype": ctx.companion})
        profile = profile.model_copy(update={"companion_choice": choice})
    return profile


def check_intake(profile: FamilyProfile) -> None:
    """Rules the schema can't express: consent, Phase 0 band, id clashes."""
    if not profile.consent.personalized_story:
        raise IntakeError("consent.personalized_story is false; cannot make a personalized book")
    bands = load_band_rules().bands
    for child in profile.children:
        if not bands[child.band].phase0:
            raise IntakeError(f"{child.id}: band {child.band} is not built in Phase 0 (§1.2)")
    people = {p.id for p in (*profile.parents, *profile.children, *profile.pets)}
    cid = companion_id(profile)
    if not cid or cid in people:
        raise IntakeError(f"companion name {profile.companion_choice.name!r} clashes or is empty")


def _write_json(path: Path, model: BaseModel, exclude: set[str] | None = None) -> None:
    """Write a model as pretty JSON, optionally dropping top-level fields."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = model.model_dump(mode="json", exclude=exclude)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_style(paths: SeriesPaths, style_id: str) -> None:
    """Write ``series/style.json``; refuse to change a series' locked style (D5)."""
    if paths.style.exists():
        current = StyleBible.model_validate_json(paths.style.read_text(encoding="utf-8"))
        if current.id != style_id:
            raise IntakeError(f"series style is locked to {current.id!r} (D5); got {style_id!r}")
        return  # keep the existing file: it may carry anchors and a pinned provider
    try:
        bible = StyleBible.model_validate(load_style_bible_raw(style_id))
    except FileNotFoundError as exc:
        raise IntakeError(str(exc)) from exc
    _write_json(paths.style, bible)


def run(ctx: StageContext) -> SeriesPaths:
    """Validate the intake and lay out ``series/<series_id>/``; returns its paths."""
    profile = load_intake(ctx)
    check_intake(profile)
    series_id = ctx.series_id or profile.id
    paths = SeriesPaths.for_series(series_id, ctx.base_dir)
    manifest = paths.manifest(1)

    start_stage(manifest, 1, STAGE_ID)
    for d in paths.dirs(character_ids(profile), episode=1):
        d.mkdir(parents=True, exist_ok=True)
    _write_style(paths, ctx.style_id or DEFAULT_STYLE)
    _write_json(paths.profile, profile, exclude={"appearance_cards"})
    for card in profile.appearance_cards:
        _write_json(paths.appearance(card.person_id), card)
    if not paths.ledger.exists():
        _write_json(paths.ledger, Ledger())
    finish_stage(manifest, 1, STAGE_ID, StageStatus.DONE)
    return paths
