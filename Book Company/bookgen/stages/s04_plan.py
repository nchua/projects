"""S4 Episode plan (SPEC §3.3 S4).

In:   bible, ledger, this episode's value, life-event note, band.
Out:  `epNN/plan.json` (EpisodePlan): title, logline, value and pattern, structure template,
      12 beats (spread, setting, characters, action, emotion, hook, text-safe side), the beat
      where the value lands (9-11), recap, teaser, three grown-up questions.
Gate: the plan judge checks 12 beats, pattern present, continuity against the ledger, no
      setting repeated from the previous episode, scare level within band, and that the story
      reads without the recap (§4.5).
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext, not_built

STAGE_ID = StageId.S4


def run(ctx: StageContext) -> None:
    """Run S4. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
