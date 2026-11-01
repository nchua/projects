"""Every craft file loads, validates, and matches the spec and its enum."""

from __future__ import annotations

from bookgen import craft
from bookgen.models import StyleBible


def test_values_match_spec_and_enum() -> None:
    """Ten values (§1.5), one enum member each."""
    values = craft.load_values()
    assert len(values) == 10
    assert {v.id for v in values} == {m.value for m in craft.Value}


def test_templates_match_spec_and_enum() -> None:
    """The six templates named in §4.4, beats within spreads 1-12."""
    templates = craft.load_templates()
    expected = {"quest", "mystery", "mishap_and_fix", "big_day", "visitor", "journey"}
    assert {t.id for t in templates} == expected == {m.value for m in craft.Template}
    for t in templates:
        for b in t.beats:
            assert 1 <= b.spreads[0] <= b.spreads[1] <= 12, (t.id, b.name)


def test_band_rules_match_spec_and_enum() -> None:
    """Bands A/B/C with §1.2 numbers; B is the Phase 0 band."""
    rules = craft.load_band_rules()
    assert set(rules.bands) == {"A", "B", "C"} == {m.value for m in craft.Band}
    b = rules.bands["B"]
    assert b.age == (4, 6) and b.words_per_book == (400, 750)
    assert b.sentences_per_spread == (2, 4) and b.body_pt == (20, 24)
    assert [k for k, r in rules.bands.items() if r.phase0] == ["B"]
    assert rules.global_.spreads_per_book == 12


def test_companions_match_spec_and_enum() -> None:
    """About eight archetypes (D13), including the ones the spec names."""
    ids = {c.id for c in craft.load_companions()}
    assert len(ids) == 8
    assert {"dragon", "robot", "fox", "cloud", "owl"} <= ids
    assert ids == {m.value for m in craft.Companion}


def test_rubric_matches_spec() -> None:
    """Eleven items numbered 1-11 with 0-3 anchors and the Phase 0 pass rule (§6.1)."""
    rubric = craft.load_rubric()
    assert [i.id for i in rubric.items] == list(range(1, 12))
    assert len({i.key for i in rubric.items}) == 11
    for item in rubric.items:
        assert sorted(item.anchors) == [0, 1, 2, 3], item.key
    assert rubric.pass_rule.min_item_score == 1 and rubric.pass_rule.min_mean == 2.3


def test_banned_phrases_include_spec_seed() -> None:
    """The §6.3 seed list is present, plus about twenty additions."""
    phrases = craft.load_banned_phrases()
    seed = {"little did they know", "learned that", "and so", "that's when ... realized"}
    assert seed <= set(phrases)
    assert len(phrases) >= 11 + 20
    assert len(phrases) == len(set(phrases))


def test_style_bibles_validate() -> None:
    """Every style bible validates as a StyleBible whose id matches its filename."""
    paths = sorted((craft.CRAFT_DIR / "style_bibles").glob("*.yaml"))
    assert paths
    for path in paths:
        bible = StyleBible.model_validate(craft.load_style_bible_raw(path.stem))
        assert bible.id == path.stem


def test_craft_guide_is_short() -> None:
    """The Craft Guide stays within about two pages."""
    words = len((craft.CRAFT_DIR / "craft_guide.md").read_text().split())
    assert 400 < words <= 1100
