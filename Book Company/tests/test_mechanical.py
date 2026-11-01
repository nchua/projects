"""Each §6.3/§6.4 mechanical check, with a passing and a failing case."""

from __future__ import annotations

import json
from typing import Any

import pytest

from bookgen.craft import load_band_rules
from bookgen.models import CheckResult, FamilyProfile, SpreadText
from bookgen.qa.mechanical import (
    Names,
    adjective_density,
    check_banned,
    check_exclamations,
    check_manuscript,
    check_names,
    check_pronouns,
    check_sentences,
    check_word_count,
    readability,
    syllables,
)
from tests.canned import demo_bible, demo_plan, good_spreads

BAND_B = load_band_rules().bands["B"]


@pytest.fixture
def profile(demo_family_raw: dict[str, Any]) -> FamilyProfile:
    """The demo family."""
    return FamilyProfile.model_validate(demo_family_raw)


@pytest.fixture
def names(profile: FamilyProfile) -> Names:
    """Names from the demo family and canned bible."""
    return Names.build(profile, demo_bible())


def _with(spread: int, text: str) -> list[SpreadText]:
    """The good manuscript with one spread's text replaced."""
    out = good_spreads()
    out[spread - 1] = SpreadText(spread=spread, text=text)
    return out


def _failed(checks: list[CheckResult]) -> list[tuple[str, int | None]]:
    """(code, spread) of each failing check."""
    return [(c.code, c.spread) for c in checks if not c.passed]


def test_good_manuscript_passes_everything(profile: FamilyProfile) -> None:
    """The canned manuscript is a clean band-B book: every check passes."""
    checks, stats = check_manuscript(good_spreads(), demo_plan(), profile, demo_bible())
    assert _failed(checks) == []
    assert 400 <= stats["words"] <= 750 and stats["fk_grade"] <= 2.5


def test_word_count_band() -> None:
    """Below the band's 400-word floor fails."""
    assert check_word_count(good_spreads(), BAND_B).passed
    short = [SpreadText(spread=i, text="Toast hopped. Maya laughed.") for i in range(1, 13)]
    result = check_word_count(short, BAND_B)
    assert not result.passed and result.value == 48


def test_sentences_per_spread_and_cap() -> None:
    """One sentence on a spread, or a 15-word sentence, fails on that spread."""
    assert _failed(check_sentences(good_spreads(), BAND_B)) == []
    one = _with(3, "Toast went up the hill.")
    assert _failed(check_sentences(one, BAND_B)) == [("sentences_per_spread", 3)]
    long = _with(5, "Toast ran. " + " ".join(["word"] * 15) + ". Maya laughed.")
    assert _failed(check_sentences(long, BAND_B)) == [("sentence_length", 5)]


def test_banned_phrases_with_wildcard_and_curly_quotes() -> None:
    """Plain phrases, ``...`` wildcards and curly apostrophes all match; clean text passes."""
    assert _failed(check_banned(good_spreads())) == []
    plain = _with(2, "Toast had a magical adventure. Maya laughed.")
    assert _failed(check_banned(plain)) == [("banned_phrases", 2)]
    wildcard = _with(4, "That’s when Maya finally realized the trick. Toast clapped.")
    assert _failed(check_banned(wildcard)) == [("banned_phrases", 4)]
    near_miss = _with(4, "That's when Maya ran. She realized it later.")  # across sentences
    assert _failed(check_banned(near_miss)) == []


def test_adjective_density(names: Names) -> None:
    """Lexicon adjectives over 1 per 8 words fail the cap."""
    assert adjective_density(good_spreads(), names) <= 0.125
    gushing = [
        SpreadText(spread=i, text="The big red shiny soft warm happy kite flew.")
        for i in range(1, 13)
    ]
    assert adjective_density(gushing, names) > 0.125


def test_exclamations() -> None:
    """Two exclamation marks on one spread fails."""
    assert _failed(check_exclamations(good_spreads(), 1)) == []
    loud = _with(7, "Toast flew! Maya cheered!")
    assert _failed(check_exclamations(loud, 1)) == [("exclamations", 7)]


def test_names_exact_and_parent_terms(names: Names) -> None:
    """Misspelt, lower-cased names and the wrong parent term fail; correct ones pass."""
    assert _failed(check_names(good_spreads(), names)) == []
    misspelt = _with(2, "Maia ran up the hill. Toast followed.")
    assert _failed(check_names(misspelt, names)) == [("names_exact", 2)]
    lower = _with(3, "Then maya ran. Toast followed.")
    assert _failed(check_names(lower, names)) == [("names_exact", 3)]
    term = _with(4, "Mom waved from the door. Maya waved back.")
    result = check_names(term, names)
    assert _failed(result) == [("names_exact", 4)] and "mama" in result[0].detail
    ok_term = _with(4, "Mama waved from the door. Appa laughed.")
    assert _failed(check_names(ok_term, names)) == []


def test_pronouns_belong_to_someone_present(names: Names) -> None:
    """A gendered pronoun with nobody present who uses it fails on that spread."""
    plan = demo_plan()
    assert _failed(check_pronouns(good_spreads(), plan, names)) == []
    plan.beats[0] = plan.beats[0].model_copy(update={"characters": ["maya"]})
    stray = _with(1, "Maya climbed the hill. He waved at her.")
    assert _failed(check_pronouns(stray, plan, names)) == [("pronouns", 1)]


def test_readability_and_syllables(names: Names) -> None:
    """Simple text grades low; long polysyllabic text grades above band B's 2.5."""
    assert syllables("dragon") == 2 and syllables("hope") == 1 and syllables("little") == 2
    assert readability(good_spreads(), names)["fk_grade"] <= 2.5
    dense = [
        SpreadText(
            spread=i,
            text="Consequently the extraordinary meteorological circumstances necessitated "
            "considerable improvisation. Toast concurred.",
        )
        for i in range(1, 13)
    ]
    assert readability(dense, names)["fk_grade"] > 2.5


def test_names_ignore_proper_nouns_in_readability(profile: FamilyProfile) -> None:
    """Long names are excluded from Flesch-Kincaid (§6.4)."""
    raw = json.loads(json.dumps(profile.model_dump(mode="json")))
    raw["children"][0]["name"] = "Anastasiabella"
    long_name = FamilyProfile.model_validate(raw)
    bible = demo_bible()
    cast = [
        c.model_copy(update={"name": "Anastasiabella"}) if c.id == "maya" else c for c in bible.cast
    ]
    names = Names.build(long_name, bible.model_copy(update={"cast": cast}))
    text = [
        SpreadText(spread=i, text="Anastasiabella ran. Anastasiabella hid.") for i in range(1, 13)
    ]
    assert readability(text, names)["fk_grade"] < 0  # only "ran", "hid" counted
