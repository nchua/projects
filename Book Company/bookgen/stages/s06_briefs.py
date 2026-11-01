"""S6 Illustration briefs (SPEC §3.3 S6).

In:   manuscript, plan, bible, sheets, style bible.
Out:  `epNN/briefs.json` (IllustrationBrief per spread plus cover, recap and teaser): scene in
      concrete nouns, characters with pose and expression, shot, text-safe area, palette and time
      of day, continuity props, negatives.
Gate: lint, every present character has a sheet, text-safe side matches the plan.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext, not_built

STAGE_ID = StageId.S6


def run(ctx: StageContext) -> None:
    """Run S6. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    not_built(STAGE_ID)
