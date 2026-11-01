"""S5 Manuscript (SPEC §3.3 S5).

In:   plan, Craft Guide, band rules, ledger (names, voices).
Out:  `epNN/manuscript.json` (Manuscript): text per spread plus read-aloud notes. Loop: writer
      drafts -> judge critiques against the rubric in a separate call -> writer revises -> at most
      two rounds -> mechanical checks (word counts per band, banned phrases, readability, exact
      name spellings, pronouns).
Gate: judge >= bar and mechanical checks pass, else flag.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S5


def run(ctx: StageContext) -> None:
    """Run S5. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
