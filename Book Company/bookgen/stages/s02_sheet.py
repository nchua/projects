"""S2 Character sheet (SPEC §3.3 S2).

In:   appearance card, style bible, photos as references only where the provider permits
      [VERIFY-2].
Out:  4-6 candidate turnaround sheets (front, three-quarter, side, four expressions, signature
      outfit) -> parent picks -> `characters/<id>/sheet.png` plus `sheet_crops/`. The companion
      gets a sheet from its archetype plus the child's colour and name choices; cameos likewise.
Gate: vision judge checks each candidate against the card before the parent sees it;
      the parent picks one.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S2


def run(ctx: StageContext) -> None:
    """Run S2. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
