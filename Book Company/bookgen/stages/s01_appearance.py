"""S1 Appearance card (SPEC §3.3 S1).

In:   3-5 photos per person, or a written description for L1.
Out:  `characters/<id>/appearance.json` (AppearanceCard): hair, skin tone id from the fixed
      10-swatch palette, eyes, glasses/assistive devices, features, height class, three
      suggested signature outfits. Claude vision with structured output.
Gate: the parent reviews and edits the card and picks the signature outfit.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S1


def run(ctx: StageContext) -> None:
    """Run S1. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
