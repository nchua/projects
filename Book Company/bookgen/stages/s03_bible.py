"""S3 Series bible (SPEC §3.3 S3).

In:   profile, cards, companion, value priorities, parent notes. Episode 1 only.
Out:  `series/bible.json` (SeriesBible): world (name, 5-8 locations), cast, tone and humor
      register, naming conventions, the season (goal, six loglines, finale shape), forbidden list
      from parent exclusions, style id. Also `series/style_anchors/*.png`: 3-5 key locations in
      the chosen style.
Gate: coherence judge, human read (§3.2).
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import Cadence, StageContext, StageResult, not_built

STAGE_ID = StageId.S3
CADENCE = Cadence.ONCE_PER_SERIES


def check(ctx: StageContext) -> None:
    """Refuse before anything is written: this stage is not built yet."""
    not_built(STAGE_ID)


def run(ctx: StageContext) -> StageResult:
    """Run S3. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
