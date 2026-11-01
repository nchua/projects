"""S13 Ledger update (SPEC §3.3 S13).

In:   approved manuscript and plan.
Out:  updated `series/ledger.json` (Ledger, §4.3). Claude extracts new facts, threads, gags and
      the next hook.
Gate: the diff is shown before it is accepted.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S13


def run(ctx: StageContext) -> None:
    """Run S13. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
