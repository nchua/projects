"""S7 Image generation (SPEC §3.3 S7).

In:   brief, sheet crops for every present character, 2-3 style anchors.
Out:  `epNN/images/sNN_cK.png`, three candidates per spread, seed and prompt hash logged.
      Runs through the ImageProvider adapter (§8.3). The brief-to-prompt rendering lives in
      this module (§8.6), so a provider swap is one adapter file.
Gate: none stated in §3.3 (QA is S8).
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import Cadence, StageContext, StageResult, not_built

STAGE_ID = StageId.S7
CADENCE = Cadence.PER_EPISODE


def check(ctx: StageContext) -> None:
    """Refuse before anything is written: this stage is not built yet."""
    not_built(STAGE_ID)


def run(ctx: StageContext) -> StageResult:
    """Run S7. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
