"""Workout session and exercise performance models."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class WeightUnit(str, Enum):
    """Weight measurement unit."""

    LB = "lb"
    KG = "kg"


# Conversion factors
LB_TO_KG = Decimal("0.45359237")
KG_TO_LB = Decimal("2.20462262")


class SetRecord(BaseModel):
    """A single set within an exercise."""

    reps: int = Field(ge=1, description="Number of repetitions")
    weight: Decimal = Field(ge=0, description="Weight used")
    weight_unit: WeightUnit = WeightUnit.LB
    rir: Optional[int] = Field(None, ge=0, le=5, description="Reps in Reserve")
    rpe: Optional[float] = Field(None, ge=5, le=10, description="Rate of Perceived Exertion")
    is_warmup: bool = False
    is_failure: bool = False
    tempo: Optional[str] = None  # e.g., "3-1-2-0"
    notes: Optional[str] = None

    @field_validator("weight", mode="before")
    @classmethod
    def coerce_weight(cls, v: float | int | str | Decimal) -> Decimal:
        return Decimal(str(v))

    @property
    def weight_kg(self) -> Decimal:
        """Return weight in kilograms."""
        if self.weight_unit == WeightUnit.KG:
            return self.weight
        return (self.weight * LB_TO_KG).quantize(Decimal("0.01"))

    @property
    def weight_lb(self) -> Decimal:
        """Return weight in pounds."""
        if self.weight_unit == WeightUnit.LB:
            return self.weight
        return (self.weight * KG_TO_LB).quantize(Decimal("0.1"))

    def to_canonical_weight(self, unit: WeightUnit = WeightUnit.LB) -> Decimal:
        """Convert weight to specified unit."""
        if unit == WeightUnit.LB:
            return self.weight_lb
        return self.weight_kg


class ExercisePerformance(BaseModel):
    """All sets for one exercise in a session."""

    exercise_name: str = Field(description="User-provided exercise name")
    canonical_id: Optional[str] = None  # Set after normalization
    variation: Optional[str] = None  # e.g., "close grip", "pause", "tempo"
    equipment: Optional[str] = None  # e.g., "barbell", "dumbbell", "cable"
    sets: list[SetRecord]
    notes: Optional[str] = None

    @property
    def working_sets(self) -> list[SetRecord]:
        """Return only non-warmup sets."""
        return [s for s in self.sets if not s.is_warmup]

    @property
    def total_reps(self) -> int:
        """Total reps across working sets."""
        return sum(s.reps for s in self.working_sets)

    @property
    def total_volume_lb(self) -> Decimal:
        """Total volume (weight * reps) in pounds."""
        return sum(s.weight_lb * s.reps for s in self.working_sets)

    @property
    def top_set(self) -> SetRecord | None:
        """Return the highest weight working set."""
        working = self.working_sets
        if not working:
            return None
        return max(working, key=lambda s: s.weight_lb)


class WorkoutSession(BaseModel):
    """A single training session."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    date: date
    start_time: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    exercises: list[ExercisePerformance]
    session_rpe: Optional[float] = Field(None, ge=1, le=10)
    notes: Optional[str] = None
    program_block_id: Optional[str] = None
    location: Optional[str] = None  # e.g., "home gym", "commercial gym"

    @model_validator(mode="after")
    def validate_session(self) -> "WorkoutSession":
        if not self.exercises:
            raise ValueError("Session must have at least one exercise")
        return self

    @property
    def total_sets(self) -> int:
        """Total working sets in session."""
        return sum(len(ex.working_sets) for ex in self.exercises)

    @property
    def total_volume_lb(self) -> Decimal:
        """Total session volume in pounds."""
        return sum(ex.total_volume_lb for ex in self.exercises)

    @property
    def exercise_names(self) -> list[str]:
        """List of exercise names in order performed."""
        return [ex.exercise_name for ex in self.exercises]


class WorkoutSessionInput(BaseModel):
    """Input format for ingesting workout data."""

    workout_session: WorkoutSession
