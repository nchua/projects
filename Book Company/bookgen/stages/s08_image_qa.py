"""S8 Image QA and pick (SPEC §3.3 S8).

In:   candidates, sheets, brief.
Out:  `epNN/qa_images.json`, chosen `sNN.png`. Vision judge scores each candidate (QAResult):
      identity per character 0-3, character count, expression, no text, anatomy, quiet text-safe
      area, band-safe, no face across the gutter.
Gate: best candidate wins if >= bar; otherwise regenerate with the judge's notes, up to three
      rounds, then flag for the editor.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import Cadence, StageContext, StageResult, not_built

STAGE_ID = StageId.S8
CADENCE = Cadence.PER_EPISODE


def check(ctx: StageContext) -> None:
    """Refuse before anything is written: this stage is not built yet."""
    not_built(STAGE_ID)


def run(ctx: StageContext) -> StageResult:
    """Run S8. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
