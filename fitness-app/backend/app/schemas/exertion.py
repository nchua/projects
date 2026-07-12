"""
Exertion analytics Pydantic schemas (ARISE v2 spec §7.2 / §13.5-13.6).

Contract-mirror note: canonical shapes for the iOS ``ExertionWeekPoint`` and
``CardiacCostResponse`` structs in APITypes.swift.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel


class ExertionWeekPoint(BaseModel):
    """One ISO week of unified-strain + volume data (spec §13.5)."""
    week_start: str                      # YYYY-MM-DD (Monday)
    strain_total: Optional[float] = None  # None when no strain data that week
    strain_avg: Optional[float] = None
    workout_count: int
    volume_lb: float
    zone_seconds: Dict[str, int]         # {z1..z5}, may be empty


class MatchedSet(BaseModel):
    """The (weight, reps) group cardiac cost is normalized on."""
    weight: float
    reps: int


class CardiacCostPoint(BaseModel):
    """Weekly median ΔHR for the matched set group."""
    week_start: str                      # YYYY-MM-DD (Monday)
    delta_hr_median: float
    n_sets: int


class CardiacCostResponse(BaseModel):
    """Response for GET /analytics/exercise/{id}/cardiac-cost (spec §13.6)."""
    exercise_id: str
    matched_set: Optional[MatchedSet] = None  # None when no matched group
    points: List[CardiacCostPoint]
    percent_change: Optional[float] = None
    trend_direction: str                 # improving | regressing | stable | insufficient_data
    caveats: List[str]
