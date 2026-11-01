"""S7 Image generation (SPEC §3.3 S7).

In:   brief, sheet crops for every present character, 2-3 style anchors.
Out:  `epNN/images/sNN_cK.png`, three candidates per spread, seed and prompt hash logged.
      Runs through the ImageProvider adapter (§8.3). The brief-to-prompt rendering lives in
      this module (§8.6), so a provider swap is one adapter file.
Gate: none stated in §3.3 (QA is S8).

Session 3 builds the rendering half (``render_prompt``, ``select_references``,
``image_prompt_hash``) so the bake-off uses exactly what S7 will; ``run`` comes in
session 4. Template: ``craft/prompts/image.md``. The no-text negative (D4) and
"not photorealistic" (D3) are always appended, whatever the brief says.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from bookgen.models import (
    AppearanceCard,
    CastMember,
    IllustrationBrief,
    StageId,
    StyleBible,
)
from bookgen.prompts import load_prompt
from bookgen.stages.base import Cadence, StageContext, StageResult, not_built

STAGE_ID = StageId.S7
CADENCE = Cadence.PER_EPISODE

ALWAYS_NEGATIVE = [
    "any text, letters, numbers, signs, labels or writing",
    "photorealism or 3D render",
]
"""Appended to every prompt: D4 (no text in images) and D3 (illustrated, never photoreal).
Phrased as things to leave out, because the template says "Do not include:"."""

CROP_ORDER = ("front", "three_quarter", "full_body")
"""Sheet crop stems in ``characters/<id>/sheet_crops/`` per §5.4 (face front,
three-quarter, full body), most useful first."""

_LEADING_NEGATION = re.compile(r"^\s*(?:no|not|never|without|avoid)\s+", re.IGNORECASE)
_SPEC_TAG = re.compile(r"\s*\((?:D|§)\d+[^)]*\)")


def as_exclusion(negative: str) -> str:
    """``'no lettering'`` -> ``'lettering'``: the template already says "Do not include"."""
    return _LEADING_NEGATION.sub("", negative).strip()


def style_text(style: StyleBible) -> str:
    """The locked style in words: attributes, line, lighting; no hex codes or spec tags.

    Hex codes and tags like ``(D4)`` are left out because image models sometimes paint
    such strings into the picture; the palette reaches the model through the anchors.
    """
    parts = [*style.attributes, f"line: {style.line}", f"lighting: {style.lighting}"]
    return "; ".join(_SPEC_TAG.sub("", p) for p in parts)


def describe(member: CastMember, card: AppearanceCard | None) -> str:
    """Who the character is, plus the card details image models drift on."""
    if card is None:
        return f"{member.name} ({member.role}): {member.description}"
    looks = [
        f"{card.hair.colour} {card.hair.texture} hair, {card.hair.length}, {card.hair.style}",
        f"{card.eyes} eyes",
        "wears glasses" if card.glasses else "",
        *card.assistive_devices,
        *card.features,
        f"wearing {card.signature_outfit}",
    ]
    return f"{member.name} ({member.role}): " + "; ".join(x for x in looks if x)


def render_prompt(
    brief: IllustrationBrief,
    style: StyleBible,
    cast: Mapping[str, CastMember],
    cards: Mapping[str, AppearanceCard],
) -> str:
    """The provider prompt for one brief: style, scene, who is where, text-safe area, negatives."""
    lines = []
    for c in brief.characters:
        member = cast.get(c.id) or CastMember(
            id=c.id, name=c.id, role="side", pronouns="they/them", description=""
        )
        lines.append(
            f"- {describe(member, cards.get(c.id))}. Pose: {c.pose}. Expression: {c.expression}."
        )
    side = f"{brief.text_side} half of the image" if brief.text_side else "area described here"
    text_area = f"{side} quiet ({brief.text_safe_area})"
    return load_prompt("image").render(
        style=style_text(style),
        scene=brief.scene,
        shot=brief.shot,
        characters="\n".join(lines) or "- (no characters)",
        props=", ".join(brief.continuity_props) or "none",
        palette=brief.palette_notes,
        text_area=text_area,
        negatives="; ".join(
            dict.fromkeys(as_exclusion(n) for n in [*brief.negatives, *ALWAYS_NEGATIVE])
        ),
    )


def select_references(
    brief: IllustrationBrief,
    character_dir: Mapping[str, Path],
    anchors: Sequence[Path],
    max_refs: int,
) -> list[Path]:
    """Reference images for one brief, best first, at most ``max_refs`` (§5.4).

    One image per present character first (front crop, else the whole sheet), then up to
    three style anchors, then further crops per character. A character with no sheet on
    disk contributes nothing (S6 already flags that).
    """
    per_char: list[list[Path]] = []
    for c in brief.characters:
        folder = character_dir.get(c.id)
        if folder is None:
            continue
        crops = [folder / "sheet_crops" / f"{stem}.png" for stem in CROP_ORDER]
        found = [p for p in crops if p.exists()] or [
            p for p in [folder / "sheet.png"] if p.exists()
        ]
        if found:
            per_char.append(found)
    ordered = [imgs[0] for imgs in per_char] + list(anchors[:3])
    ordered += [img for imgs in per_char for img in imgs[1:]]
    return ordered[:max_refs]


def image_prompt_hash(prompt: str, references: Sequence[Path]) -> str:
    """SHA-256 over the prompt and every reference's bytes (§3.1 replay key, S7 naming)."""
    h = hashlib.sha256(prompt.encode())
    for ref in references:
        h.update(hashlib.sha256(ref.read_bytes()).digest())
    return h.hexdigest()


def check(ctx: StageContext) -> None:
    """Refuse before anything is written: the stage run is session 4."""
    not_built(STAGE_ID)


def run(ctx: StageContext) -> StageResult:
    """Run S7. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
