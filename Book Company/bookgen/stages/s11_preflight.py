"""S11 Preflight (SPEC §3.3 S11).

In:   the three PDFs from S10.
Out:  `preflight.json`. Checks: 32 pages, page size with bleed, effective image DPI >= 300, fonts
      embedded, colour profile per printer spec [VERIFY-3], text in safe zone, no empty spreads,
      spine width matches the printer's calculator.
Gate: any failure blocks S12.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import Cadence, StageContext, StageResult, not_built

STAGE_ID = StageId.S11
CADENCE = Cadence.PER_EPISODE


def check(ctx: StageContext) -> None:
    """Refuse before anything is written: this stage is not built yet."""
    not_built(STAGE_ID)


def run(ctx: StageContext) -> StageResult:
    """Run S11. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
