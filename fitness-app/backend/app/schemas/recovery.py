"""
Recovery/Cooldown Pydantic schemas for muscle recovery tracking.

Science-based recovery times:
- Large muscles (Quads, Hamstrings, Chest): 48-72 hours
- Medium muscles (Shoulders): 48 hours
- Small muscles (Biceps, Triceps): 24-48 hours
"""
from pydantic import BaseModel
from typing import List
from enum import Enum


class MuscleGroup(str, Enum):
    """Target muscle groups for recovery tracking"""
    CHEST = "chest"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    SHOULDERS = "shoulders"


class RecoveryStatus(str, Enum):
    """Recovery status for a muscle group"""
    RECOVERING = "recovering"
    RECOVERED = "recovered"


class AffectedExercise(BaseModel):
    """Exercise that affected a muscle group"""
    exercise_id: str
    exercise_name: str
    workout_date: str
    fatigue_type: str  # "primary" or "secondary"


class MuscleRecoveryStatus(BaseModel):
    """Recovery status for a single muscle group"""
    muscle_group: str
    status: str
    recovery_percent: float  # 0-100, 100 = fully recovered
    hours_remaining: int  # hours until fully recovered
    last_trained: str  # ISO datetime
    affected_exercises: List[AffectedExercise]


class RecoveryResponse(BaseModel):
    """Response for recovery endpoint"""
    fatigued_muscles: List[MuscleRecoveryStatus]
    generated_at: str
