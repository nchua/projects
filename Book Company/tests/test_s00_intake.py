"""S0 creates the §3.4 layout and the manifest, and is safe to re-run."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bookgen.manifest import read_manifest
from bookgen.models import (
    AppearanceCard,
    Companion,
    FamilyProfile,
    Ledger,
    StageId,
    StageStatus,
    StyleBible,
)
from bookgen.paths import SeriesPaths
from bookgen.stages import StageContext, run_range
from bookgen.stages.s00_intake import IntakeError, with_series_id

WriteFamily = Callable[[dict[str, Any]], Path]


def _ctx(
    tmp_path: Path,
    family: Path,
    *,
    series_id: str | None = None,
    style_id: str | None = None,
    companion: Companion | None = None,
) -> StageContext:
    """An S0 context writing under ``tmp_path``."""
    return StageContext(
        series_id=series_id,
        base_dir=tmp_path,
        family_path=family,
        style_id=style_id,
        companion=companion,
    )


def run(ctx: StageContext) -> SeriesPaths:
    """Run S0 through the runner, as ``book init-series`` does."""
    full = with_series_id(ctx)
    run_range(full, [StageId.S0])
    return full.paths


def test_init_creates_layout_and_manifest(tmp_path: Path, demo_family_path: Path) -> None:
    """Every §3.4 directory and S0 artifact exists and validates."""
    paths = run(_ctx(tmp_path, demo_family_path, style_id="gouache-warm"))
    assert paths.root == tmp_path / "demo"
    for rel in [
        "family",
        "series/style_anchors",
        "ep01/images",
        "ep01/print",
        "ep01/logs",
        "characters/maya/sheet_crops",
        "characters/maya/candidates",
        "characters/toast",  # companion, by its given name
        "characters/pickles",  # pet cameo (consented)
    ]:
        assert (paths.root / rel).is_dir(), rel

    profile_raw = json.loads(paths.profile.read_text())
    assert "appearance_cards" not in profile_raw
    assert FamilyProfile.model_validate(profile_raw).hero.id == "maya"
    card = AppearanceCard.model_validate_json(paths.appearance("maya").read_text())
    assert card.glasses is True
    assert StyleBible.model_validate_json(paths.style.read_text()).id == "gouache-warm"
    assert Ledger.model_validate_json(paths.ledger.read_text()) == Ledger()

    manifest = read_manifest(paths.manifest(1), 1)
    rec = manifest.stages[StageId.S0]
    assert rec.status is StageStatus.DONE and rec.attempts == 1 and rec.finished


def test_rerun_is_idempotent_and_keeps_ledger(tmp_path: Path, demo_family_path: Path) -> None:
    """Re-running bumps attempts and never overwrites the ledger."""
    paths = run(_ctx(tmp_path, demo_family_path))
    paths.ledger.write_text(Ledger(next_hook="A letter arrives.").model_dump_json())
    run(_ctx(tmp_path, demo_family_path))
    assert Ledger.model_validate_json(paths.ledger.read_text()).next_hook == "A letter arrives."
    assert read_manifest(paths.manifest(1), 1).stages[StageId.S0].attempts == 2


def test_style_is_locked(tmp_path: Path, demo_family_path: Path) -> None:
    """A series cannot switch style after init (D5); unknown styles are rejected."""
    run(_ctx(tmp_path, demo_family_path, style_id="gouache-warm"))
    with pytest.raises(IntakeError, match="locked"):
        run(_ctx(tmp_path, demo_family_path, style_id="other"))
    with pytest.raises(IntakeError, match="unknown style"):
        run(_ctx(tmp_path, demo_family_path, series_id="fresh", style_id="nope"))


def test_companion_override_and_series_id(tmp_path: Path, demo_family_path: Path) -> None:
    """``--companion`` overrides the archetype; ``--series`` overrides the id."""
    paths = run(_ctx(tmp_path, demo_family_path, series_id="maya1", companion=Companion.ROBOT))
    assert paths.root.name == "maya1"
    profile = FamilyProfile.model_validate_json(paths.profile.read_text())
    assert profile.companion_choice.archetype is Companion.ROBOT


def test_intake_rules(
    tmp_path: Path, demo_family_raw: dict[str, Any], write_family: WriteFamily
) -> None:
    """Consent, Phase 0 band, companion clashes and cameo consent are enforced."""
    raw = demo_family_raw
    write = write_family

    no_consent = {**raw, "consent": {**raw["consent"], "personalized_story": False}}
    with pytest.raises(IntakeError, match="consent"):
        run(_ctx(tmp_path, write(no_consent)))

    band_a = {**raw, "children": [{**raw["children"][0], "band": "A"}]}
    with pytest.raises(IntakeError, match="Phase 0"):
        run(_ctx(tmp_path, write(band_a)))

    no_cameos = {**raw, "consent": {**raw["consent"], "family_cameos": False}}
    paths = run(_ctx(tmp_path, write(no_cameos), series_id="private"))
    assert not paths.character_dir("dana").exists()
    assert not paths.character_dir("pickles").exists()

    clash = {**raw, "companion_choice": {**raw["companion_choice"], "name": "Pickles"}}
    with pytest.raises(IntakeError, match="clashes"):
        run(_ctx(tmp_path, write(clash)))

    with pytest.raises(IntakeError, match="invalid family"):
        run(_ctx(tmp_path, write({"id": "x"})))


def test_failed_intake_writes_nothing(tmp_path: Path, demo_family_path: Path) -> None:
    """A rejected style leaves no series folder and no stale STARTED record."""
    with pytest.raises(IntakeError):
        run(_ctx(tmp_path, demo_family_path, style_id="nope"))
    assert not (tmp_path / "demo").exists()


def test_sibling_band_does_not_gate(
    tmp_path: Path, demo_family_raw: dict[str, Any], write_family: WriteFamily
) -> None:
    """Only the hero's band must be a Phase 0 band; a band-A sibling is a cameo."""
    raw = demo_family_raw
    sib = {"id": "leo", "name": "Leo", "pronouns": "he/him", "birth_month": "2024-01", "band": "A"}
    path = write_family({**raw, "children": [*raw["children"], sib]})
    assert run(_ctx(tmp_path, path)).character_dir("leo").is_dir()


def test_rerun_keeps_edited_appearance_card(tmp_path: Path, demo_family_path: Path) -> None:
    """A card edited after S0 (the S1 gate) survives a re-run."""
    paths = run(_ctx(tmp_path, demo_family_path))
    card = AppearanceCard.model_validate_json(paths.appearance("maya").read_text())
    paths.appearance("maya").write_text(
        card.model_copy(update={"skin_tone_id": 5}).model_dump_json()
    )
    run(_ctx(tmp_path, demo_family_path))
    assert (
        AppearanceCard.model_validate_json(paths.appearance("maya").read_text()).skin_tone_id == 5
    )
