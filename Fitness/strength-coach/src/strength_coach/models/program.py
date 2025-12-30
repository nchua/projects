"""Training program and mesocycle models."""

from datetime import date
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class TrainingGoal(str, Enum):
    """Primary goal for a training block."""

    STRENGTH = "strength"
    HYPERTROPHY = "hypertrophy"
    POWER = "power"
    PEAKING = "peaking"
    DELOAD = "deload"
    MAINTENANCE = "maintenance"
    GENERAL_FITNESS = "general_fitness"


class ProgramBlock(BaseModel):
    """A mesocycle or training block with specific goals."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1)
    start_date: date
    end_date: Optional[date] = None
    primary_goal: TrainingGoal
    secondary_goal: Optional[TrainingGoal] = None
    weekly_frequency: Optional[int] = Field(None, ge=1, le=7)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self) -> "ProgramBlock":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be after start_date")
        return self

    @property
    def duration_weeks(self) -> int | None:
        """Duration in weeks, if end date is set."""
        if self.end_date is None:
            return None
        delta = self.end_date - self.start_date
        return delta.days // 7

    @property
    def is_active(self) -> bool:
        """Check if block is currently active."""
        today = date.today()
        if self.end_date:
            return self.start_date <= today <= self.end_date
        return self.start_date <= today


class TrainingWeek(BaseModel):
    """Weekly training summary (computed, not stored)."""

    week_start: date
    week_end: date
    program_block_id: Optional[str] = None
    session_count: int = 0
    total_sets: int = 0
    total_volume_lb: float = 0
    avg_session_rpe: Optional[float] = None
    exercises_performed: list[str] = []
