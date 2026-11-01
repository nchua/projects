"""S10 Layout (SPEC §3.3 S10).

In:   manuscript, print images, cover image, templates.
Out:  `book_print.pdf` (interior with bleed), `cover_print.pdf` (wraparound with spine),
      `book_preview.pdf` (screen). Jinja2 HTML/CSS -> WeasyPrint. Band B body 20-24 pt, Andika,
      text inside the safe zone, never across the gutter.
Gate: auto-fit shrinks at most 10% before flagging overflow.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S10


def run(ctx: StageContext) -> None:
    """Run S10. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
