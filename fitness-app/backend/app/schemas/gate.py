"""
PR Gate Pydantic schemas (ARISE v2 spec §6.5 / §13.3).

Contract-mirror note: canonical shape for the iOS ``GateResponse`` struct in
APITypes.swift.
"""
from typing import Optional

from pydantic import BaseModel


class GateResponse(BaseModel):
    """One PR Gate (spec §13.3)."""
    id: str
    exercise_id: str
    exercise_name: str
    rank: str                     # C | B | A | S
    name: str                     # "B-Rank Gate: Bench 225×4"
    target_weight: float
    target_reps: int
    target_e1rm: float
    baseline_e1rm: float
    projected_e1rm: float
    weekly_slope: float           # lb/week at spawn
    condition_at_spawn: int
    status: str                   # open | active | cleared | expired
    spawned_at: str               # ISO8601
    expires_at: str               # ISO8601
    accepted_at: Optional[str] = None
    cleared_at: Optional[str] = None
    cleared_by_set_id: Optional[str] = None
    xp_awarded: Optional[int] = None
