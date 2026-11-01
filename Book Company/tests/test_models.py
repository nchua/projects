"""Models round-trip the JSON fixtures and enforce the spec's shape rules."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from bookgen.models import (
    Band,
    Beat,
    Companion,
    EpisodePlan,
    FamilyProfile,
    Ledger,
    Manifest,
    Review,
    StageId,
    StageRecord,
    StageStatus,
    Template,
    Value,
)


def test_family_fixture_round_trips(demo_family_raw: dict[str, Any]) -> None:
    """The fixture validates, and dump -> load is lossless."""
    raw = demo_family_raw
    family = FamilyProfile.model_validate(raw)
    assert family.hero.name == "Maya"
    assert family.hero.band is Band.B
    assert family.companion_choice.archetype is Companion.DRAGON
    assert family.value_priorities[0] is Value.PERSEVERANCE
    again = FamilyProfile.model_validate_json(family.model_dump_json())
    assert again == family
    assert json.loads(family.model_dump_json()) == raw


def test_family_rejects_unknown_value_and_companion(demo_family_raw: dict[str, Any]) -> None:
    """Values and companions must exist in the craft files."""
    raw = demo_family_raw
    with pytest.raises(ValidationError):
        FamilyProfile.model_validate({**raw, "value_priorities": ["punctuality"]})
    bad_companion = {**raw["companion_choice"], "archetype": "unicorn"}
    with pytest.raises(ValidationError):
        FamilyProfile.model_validate({**raw, "companion_choice": bad_companion})


def test_family_rejects_card_for_unknown_person(demo_family_raw: dict[str, Any]) -> None:
    """Appearance cards must refer to someone in the family."""
    raw = demo_family_raw
    card = {**raw["appearance_cards"][0], "person_id": "nobody"}
    with pytest.raises(ValidationError, match="unknown people"):
        FamilyProfile.model_validate({**raw, "appearance_cards": [card]})


def _plan(beats: list[Beat]) -> dict[str, object]:
    """A minimal plan payload around ``beats``."""
    return {
        "episode": 1,
        "title": "Toast Tries to Fly",
        "logline": "Maya helps a dragon who cannot fly.",
        "value": "perseverance",
        "pattern": ["try", "fail", "change approach", "try again"],
        "template": "quest",
        "beats": [b.model_dump() for b in beats],
        "value_lands_at": 10,
        "recap": "",
        "teaser": "Next time: a knock at the window.",
        "grownup_questions": ["a?", "b?", "c?"],
    }


def _beat(n: int) -> Beat:
    """A beat for spread ``n``."""
    return Beat(
        spread=n,
        setting="garden",
        characters=["maya", "toast"],
        action="x",
        emotion="y",
        hook="z",
        text_side="left",
    )


def test_plan_requires_twelve_ordered_beats() -> None:
    """Plans have exactly 12 beats covering spreads 1-12 in order (§3.3 S4)."""
    beats = [_beat(n) for n in range(1, 13)]
    plan = EpisodePlan.model_validate(_plan(beats))
    assert plan.template is Template.QUEST
    assert EpisodePlan.model_validate_json(plan.model_dump_json()) == plan
    with pytest.raises(ValidationError):
        EpisodePlan.model_validate(_plan(beats[:11]))
    with pytest.raises(ValidationError, match="in order"):
        EpisodePlan.model_validate(_plan([beats[1], beats[0], *beats[2:]]))
    with pytest.raises(ValidationError, match="60 words"):
        EpisodePlan.model_validate({**_plan(beats), "recap": "word " * 61})


def test_ledger_round_trip_and_summary_cap() -> None:
    """Ledger round-trips; last_summary is capped at 120 words (§4.3)."""
    ledger = Ledger.model_validate(
        {
            "facts": [{"text": "Toast cannot fly yet.", "episode": 1}],
            "lessons_covered": [{"episode": 1, "value": "perseverance"}],
            "running_gags": [{"description": "Toast hops instead of flying", "uses": 1}],
            "last_summary": "Maya and Toast built a kite.",
            "next_hook": "A letter arrives with no stamp.",
            "child_age_at_last": 5,
        }
    )
    assert Ledger.model_validate_json(ledger.model_dump_json()) == ledger
    with pytest.raises(ValidationError, match="120 words"):
        Ledger(last_summary="word " * 121)


def test_manifest_round_trip() -> None:
    """Manifest keys stages by StageId and round-trips through JSON."""
    rec = StageRecord(status=StageStatus.DONE, started=datetime(2026, 11, 1, tzinfo=UTC))
    m = Manifest(episode=1, stages={StageId.S0: rec})
    assert Manifest.model_validate_json(m.model_dump_json()) == m


def test_review_scores_use_rubric_keys() -> None:
    """Review score keys must exist in craft/judge_rubric.yaml."""
    Review(episode=1, scores={"delight": 3, "hero_agency": 2})
    with pytest.raises(ValidationError, match="unknown rubric"):
        Review(episode=1, scores={"vibes": 3})
    with pytest.raises(ValidationError):
        Review(episode=1, scores={"delight": 4})
