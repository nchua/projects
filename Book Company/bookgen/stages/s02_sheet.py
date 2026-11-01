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
from bookgen.stages.base import Cadence, StageContext, StageResult, not_built

STAGE_ID = StageId.S2
CADENCE = Cadence.PER_CHARACTER


def check(ctx: StageContext) -> None:
    """Refuse before anything is written: this stage is not built yet."""
    not_built(STAGE_ID)


def run(ctx: StageContext) -> StageResult:
    """Run S2. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
