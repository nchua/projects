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
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S8


def run(ctx: StageContext) -> None:
    """Run S8. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
