"""
Cooldown Pydantic schemas for muscle cooldown tracking.

Science-based cooldown times:
- Large muscles (Quads, Hamstrings, Chest): 48-72 hours
- Medium muscles (Shoulders): 48 hours
- Small muscles (Biceps, Triceps): 24-48 hours
"""
from pydantic import BaseModel
from typing import List
from enum import Enum


class MuscleGroup(str, Enum):
    """Target muscle groups for cooldown tracking"""
    CHEST = "chest"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    SHOULDERS = "shoulders"


class CooldownStatus(str, Enum):
    """Cooldown status for a muscle group"""
    COOLING = "cooling"
    READY = "ready"


class AffectedExercise(BaseModel):
    """Exercise that affected a muscle group"""
    exercise_id: str
    exercise_name: str
    workout_date: str
    fatigue_type: str  # "primary" or "secondary"


class MuscleCooldownStatus(BaseModel):
    """Cooldown status for a single muscle group"""
    muscle_group: str
    status: str
    cooldown_percent: float  # 0-100, 100 = fully ready
    hours_remaining: int  # hours until fully ready
    last_trained: str  # ISO datetime
    affected_exercises: List[AffectedExercise]


class CooldownResponse(BaseModel):
    """Response for cooldown endpoint"""
    muscles_cooling: List[MuscleCooldownStatus]
    generated_at: str
    age_modifier: float = 1.0  # Age-based recovery modifier (1.0 = baseline)
