"""S11 Preflight (SPEC §3.3 S11).

In:   the three PDFs from S10.
Out:  `preflight.json`. Checks: 32 pages, page size with bleed, effective image DPI >= 300, fonts
      embedded, colour profile per printer spec [VERIFY-3], text in safe zone, no empty spreads,
      spine width matches the printer's calculator.
Gate: any failure blocks S12.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S11


def run(ctx: StageContext) -> None:
    """Run S11. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
