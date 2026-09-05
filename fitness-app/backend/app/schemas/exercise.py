"""
Exercise schemas for request/response validation
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class ExerciseCreate(BaseModel):
    """Schema for creating a custom exercise"""
    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = Field(None, pattern="^(Push|Pull|Legs|Core|Accessories)$")
    primary_muscle: Optional[str] = None
    secondary_muscles: Optional[List[str]] = None


class ExerciseResponse(BaseModel):
    """Schema for exercise information in responses"""
    id: str
    name: str
    # Other names for this movement ("Lying Tricep Extension" for "Skull
    # Crushers"). The list endpoint returns one row per canonical group, so
    # clients need these to make the collapsed names searchable.
    aliases: List[str] = Field(default_factory=list)
    canonical_id: Optional[str]
    category: Optional[str]
    primary_muscle: Optional[str]
    secondary_muscles: Optional[List[str]]
    is_custom: bool
    user_id: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ============ ARISE v3 §15.1 — last performance ============

class LastPerformanceSet(BaseModel):
    weight_lb: float
    reps: int
    rpe: Optional[int] = None
    is_warmup: bool = False


class LastPerformanceResponse(BaseModel):
    """GET /exercises/{id}/last-performance — the LogView "LAST" column.

    Contract-mirror note: canonical shape for the iOS ``LastPerformanceResponse``.
    Spans the exercise's whole family (canonical alias group when the family
    is unknown) so it never disagrees with the prescription engine's anchor.
    """
    exercise_id: str
    family_id: Optional[str] = None
    date: str                       # local YYYY-MM-DD
    days_ago: int
    sets: List[LastPerformanceSet]
    best_e1rm: Optional[float] = None
    best_e1rm_date: Optional[str] = None
