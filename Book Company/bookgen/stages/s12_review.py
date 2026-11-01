"""S12 Editor review (SPEC §3.3 S12).

In:   `book_preview.pdf`, `manuscript.json`.
Out:  `review.md`, a Review (rubric scores §6.1), status `approved`. The editor edits text
      directly in `manuscript.json` and reruns from S10 (text) or S7 for one spread
      (`--spread 7`).
Gate: a human approves (D8).
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S12


def run(ctx: StageContext) -> None:
    """Run S12. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
