"""S7's brief-to-prompt rendering and reference selection (used by the bake-off too)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bookgen.craft import load_style_bible_raw
from bookgen.models import AppearanceCard, FamilyProfile, StyleBible
from bookgen.providers.images.fake import write_png
from bookgen.stages.s07_generate import prompt_hash, render_prompt, select_references
from tests.canned import demo_bible, demo_briefs


def _setup(demo_family_raw: dict[str, Any]) -> tuple[StyleBible, dict, dict[str, AppearanceCard]]:
    """Style, cast by id, and Maya's card from the fixture family."""
    style = StyleBible.model_validate(load_style_bible_raw("gouache-warm"))
    cast = {c.id: c for c in demo_bible().cast}
    cards = {c.person_id: c for c in FamilyProfile.model_validate(demo_family_raw).appearance_cards}
    return style, cast, cards


def test_prompt_has_style_cast_text_area_and_mandatory_negatives(
    demo_family_raw: dict[str, Any],
) -> None:
    """Card details for Maya, bible description for Toast, text side, D3/D4 negatives."""
    style, cast, cards = _setup(demo_family_raw)
    brief = demo_briefs().briefs[0]  # spread 1, text left
    prompt = render_prompt(brief, style, cast, cards)
    assert "opaque gouache" in prompt and "#E9A86B" in prompt
    assert "Maya (hero)" in prompt and "wears glasses" in prompt and "mustard raincoat" in prompt
    assert "Toast (companion): Teal dragon" in prompt
    assert "left half of the image quiet" in prompt
    assert "no lettering or readable text" in prompt  # the brief's own negative
    assert "signs, labels or writing" in prompt and "photorealism" in prompt  # always added
    assert "$" not in prompt  # every placeholder filled


def test_references_one_per_character_then_anchors_then_extras(tmp_path: Path) -> None:
    """Front crops first, then up to 3 anchors, then more crops; capped at max_refs."""
    dirs = {}
    for cid in ("maya", "toast"):
        crops = tmp_path / cid / "sheet_crops"
        crops.mkdir(parents=True)
        for stem in ("front", "three_quarter"):
            write_png(crops / f"{stem}.png", 2, 2, (1, 1, 1))
        dirs[cid] = tmp_path / cid
    anchors = [write_png(tmp_path / f"a{i}.png", 2, 2, (2, 2, 2)) for i in range(4)]
    brief = demo_briefs().briefs[0]
    refs = select_references(brief, dirs, anchors, max_refs=8)
    names = [f"{p.parent.parent.name}/{p.stem}" if "crops" in str(p) else p.stem for p in refs]
    assert names == [
        "maya/front",
        "toast/front",
        "a0",
        "a1",
        "a2",
        "maya/three_quarter",
        "toast/three_quarter",
    ]
    assert len(select_references(brief, dirs, anchors, max_refs=3)) == 3


def test_reference_falls_back_to_whole_sheet_and_skips_missing(tmp_path: Path) -> None:
    """No crops: use sheet.png; no folder at all: contribute nothing."""
    (tmp_path / "maya").mkdir()
    sheet = write_png(tmp_path / "maya" / "sheet.png", 2, 2, (3, 3, 3))
    refs = select_references(demo_briefs().briefs[0], {"maya": tmp_path / "maya"}, [], 8)
    assert refs == [sheet]


def test_prompt_hash_covers_reference_bytes(tmp_path: Path) -> None:
    """Same prompt, different reference pixels: different hash."""
    a = write_png(tmp_path / "a.png", 2, 2, (1, 1, 1))
    h1 = prompt_hash("p", [a])
    write_png(a, 2, 2, (9, 9, 9))
    assert prompt_hash("p", [a]) != h1 and len(h1) == 64
