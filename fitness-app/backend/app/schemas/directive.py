"""
System Directive Pydantic schemas (ARISE v2 spec §5.3 / §13.2).

Contract-mirror note: canonical shape for the iOS ``DirectiveResponse``
struct in APITypes.swift.
"""
from typing import List, Optional

from pydantic import BaseModel


class DirectiveResponse(BaseModel):
    """One daily directive."""
    id: str
    date: str                        # YYYY-MM-DD (user-local day)
    directive_type: str              # rest | streak_save | reclaim_volume |
    #                                  break_plateau | frequency | gate_reminder | maintain
    message: str
    params: Optional[dict] = None    # type-specific: lift, muscle, delta_pct, ...
    xp_reward: int
    is_completed: bool
    completed_at: Optional[str] = None  # ISO8601


class DirectiveHistoryResponse(BaseModel):
    """Response for GET /directive/history."""
    directives: List[DirectiveResponse]
