"""Manifest records upsert per stage and accumulate attempts and cost (§3.1)."""

from __future__ import annotations

from pathlib import Path

from bookgen.manifest import add_flag, finish_stage, read_manifest, start_stage
from bookgen.models import StageId, StageStatus


def test_attempts_and_cost_accumulate(tmp_path: Path) -> None:
    """Two runs of S5 leave one record with attempts=2 and summed cost."""
    path = tmp_path / "ep01" / "manifest.json"
    for cost in (0.40, 0.25):
        start_stage(path, 1, StageId.S5)
        finish_stage(path, 1, StageId.S5, StageStatus.DONE, model="claude-opus-5-5", cost_usd=cost)
    rec = read_manifest(path, 1).stages[StageId.S5]
    assert rec.attempts == 2
    assert round(rec.cost_usd, 2) == 0.65
    assert rec.model == "claude-opus-5-5"


def test_flags_append(tmp_path: Path) -> None:
    """A failed gate is a flag in the manifest, not an exception."""
    path = tmp_path / "manifest.json"
    add_flag(path, 1, StageId.S5, "word_count_high", "812 words > 750 for band B")
    add_flag(path, 1, StageId.S8, "identity_low", "Maya's glasses missing", spread=7)
    flags = read_manifest(path, 1).flags
    assert [f.code for f in flags] == ["word_count_high", "identity_low"]
    assert flags[1].spread == 7 and not flags[1].resolved
