"""S0 creates the §3.4 layout and the manifest, and is safe to re-run."""

from __future__ import annotations

import json
from pathlib import Path

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
from bookgen.stages import StageContext
from bookgen.stages.s00_intake import IntakeError, run


def _ctx(tmp_path: Path, family: Path, **kw: object) -> StageContext:
    """An S0 context writing under ``tmp_path``."""
    kw.setdefault("series_id", None)
    return StageContext(base_dir=tmp_path, family_path=family, **kw)  # type: ignore[arg-type]


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


def test_intake_rules(tmp_path: Path, demo_family_path: Path) -> None:
    """Consent, Phase 0 band and cameo consent are enforced."""
    raw = json.loads(demo_family_path.read_text())

    def write(data: dict[str, object]) -> Path:
        path = tmp_path / "f.json"
        path.write_text(json.dumps(data))
        return path

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

    with pytest.raises(IntakeError, match="invalid family"):
        run(_ctx(tmp_path, write({"id": "x"})))
