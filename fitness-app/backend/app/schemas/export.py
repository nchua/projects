"""
Schemas for the read-only owner export (``GET /export/workouts``).

Every list is a flat table so a spreadsheet client can write one tab per key
without reshaping. Weights are lb; days are the lifter's local calendar day.
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class ExportSessionRow(BaseModel):
    """One workout session (strength or cardio)."""
    session_id: str
    day: date
    week_start: date
    name: Optional[str] = None
    kind: str  # "strength" | "cardio"
    activity_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    session_rpe: Optional[int] = None
    exercises: int
    working_sets: int
    total_reps: int
    tonnage_lb: float
    distance_miles: Optional[float] = None
    avg_heart_rate: Optional[int] = None
    peak_heart_rate: Optional[int] = None
    strain: Optional[float] = None
    hr_source: Optional[str] = None
    training_load: Optional[float] = None
    notes: Optional[str] = None


class ExportSetRow(BaseModel):
    """One logged set, warm-ups included (flagged)."""
    session_id: str
    day: date
    week_start: date
    exercise: str
    family: Optional[str] = None
    primary_muscle: Optional[str] = None
    exercise_order: int
    set_number: int
    weight_lb: float
    reps: int
    is_warmup: bool
    is_bodyweight: bool
    rpe: Optional[int] = None
    rir: Optional[int] = None
    e1rm: Optional[float] = None
    volume_lb: float  # weight_lb × reps; 0 for warm-ups


class ExportWeeklyVolumeRow(BaseModel):
    """Per-week totals over working sets (Monday-start weeks)."""
    week_start: date
    strength_sessions: int
    cardio_sessions: int
    working_sets: int
    total_reps: int
    tonnage_lb: float
    cardio_miles: float


class ExportWeeklyMuscleRow(BaseModel):
    """Per-week working sets and tonnage for one primary muscle."""
    week_start: date
    primary_muscle: str
    working_sets: int
    total_reps: int
    tonnage_lb: float


class ExportPRRow(BaseModel):
    """One personal record."""
    day: date
    exercise: str
    pr_type: str
    e1rm: Optional[float] = None
    weight_lb: Optional[float] = None
    reps: Optional[int] = None


class ExportBodyweightRow(BaseModel):
    """One bodyweight entry."""
    day: date
    weight_lb: float
    source: str


class WorkoutExportResponse(BaseModel):
    """Everything the Sheet mirrors, for the window ``[start, end]``."""
    generated_at: datetime
    start: date
    end: date
    sessions: List[ExportSessionRow]
    sets: List[ExportSetRow]
    weekly_volume: List[ExportWeeklyVolumeRow]
    weekly_muscle_volume: List[ExportWeeklyMuscleRow]
    prs: List[ExportPRRow]
    bodyweight: List[ExportBodyweightRow]
