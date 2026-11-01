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
from bookgen.stages.base import Cadence, StageContext, StageResult, not_built

STAGE_ID = StageId.S5
CADENCE = Cadence.PER_EPISODE


def check(ctx: StageContext) -> None:
    """Refuse before anything is written: this stage is not built yet."""
    not_built(STAGE_ID)


def run(ctx: StageContext) -> StageResult:
    """Run S5. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
