"""Activity and daily metrics models for fitness tracker data."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ActivitySource(str, Enum):
    """Source of activity data."""

    WHOOP = "whoop"
    APPLE_FITNESS = "apple_fitness"
    GARMIN = "garmin"
    FITBIT = "fitbit"
    MANUAL = "manual"


class CardioWorkoutType(str, Enum):
    """Types of cardio/activity workouts."""

    WALKING = "walking"
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
    HIIT = "hiit"
    ROWING = "rowing"
    ELLIPTICAL = "elliptical"
    STRENGTH = "strength"
    YOGA = "yoga"
    OTHER = "other"


class HeartRateZone(BaseModel):
    """Time spent in a heart rate zone."""

    zone_number: int = Field(ge=1, le=5)
    zone_name: Optional[str] = None  # e.g., "Fat Burn", "Cardio", "Peak"
    minutes: int = Field(ge=0)
    avg_hr: Optional[int] = None


class CardioActivity(BaseModel):
    """A single cardio/activity workout."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    activity_type: CardioWorkoutType
    start_time: Optional[datetime] = None
    duration_minutes: int = Field(ge=0)
    calories_burned: Optional[int] = Field(None, ge=0)
    avg_heart_rate: Optional[int] = Field(None, ge=30, le=250)
    max_heart_rate: Optional[int] = Field(None, ge=30, le=250)
    distance_miles: Optional[Decimal] = Field(None, ge=0)
    heart_rate_zones: Optional[list[HeartRateZone]] = None
    notes: Optional[str] = None

    @field_validator("distance_miles", mode="before")
    @classmethod
    def coerce_distance(cls, v: float | int | str | Decimal | None) -> Decimal | None:
        if v is None:
            return None
        return Decimal(str(v))


class DailyActivityEntry(BaseModel):
    """Daily activity summary from fitness trackers."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    date: date
    source: ActivitySource

    # Core metrics
    steps: Optional[int] = Field(None, ge=0)
    total_calories: Optional[int] = Field(None, ge=0)  # Total daily burn
    active_calories: Optional[int] = Field(None, ge=0)  # Exercise calories
    active_minutes: Optional[int] = Field(None, ge=0)

    # Whoop-specific metrics
    strain: Optional[float] = Field(None, ge=0, le=21)  # Whoop strain 0-21
    recovery_score: Optional[int] = Field(None, ge=0, le=100)
    hrv: Optional[int] = Field(None, ge=0)  # Heart rate variability (ms)
    resting_heart_rate: Optional[int] = Field(None, ge=30, le=120)

    # Sleep metrics (often from same screenshot)
    sleep_hours: Optional[float] = Field(None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(None, ge=0, le=100)  # Percentage

    # Apple Fitness specific (activity rings)
    exercise_minutes: Optional[int] = Field(None, ge=0)  # Green ring
    stand_hours: Optional[int] = Field(None, ge=0, le=24)  # Blue ring
    move_calories: Optional[int] = Field(None, ge=0)  # Red ring

    # Individual workout activities for the day
    activities: list[CardioActivity] = Field(default_factory=list)

    notes: Optional[str] = None
    raw_ocr_text: Optional[str] = None  # Store original extraction for debugging

    @field_validator("strain", mode="before")
    @classmethod
    def coerce_strain(cls, v: float | int | str | None) -> float | None:
        if v is None:
            return None
        return float(v)

    @field_validator("sleep_hours", mode="before")
    @classmethod
    def coerce_sleep_hours(cls, v: float | int | str | None) -> float | None:
        if v is None:
            return None
        return float(v)

    @property
    def has_whoop_data(self) -> bool:
        """Check if entry has Whoop-specific metrics."""
        return any([
            self.strain is not None,
            self.recovery_score is not None,
            self.hrv is not None,
        ])

    @property
    def has_apple_rings(self) -> bool:
        """Check if entry has Apple Fitness ring data."""
        return any([
            self.move_calories is not None,
            self.exercise_minutes is not None,
            self.stand_hours is not None,
        ])

    @property
    def total_activity_duration(self) -> int:
        """Total duration of all logged activities in minutes."""
        return sum(a.duration_minutes for a in self.activities)

    @property
    def total_activity_calories(self) -> int:
        """Total calories from all logged activities."""
        return sum(a.calories_burned or 0 for a in self.activities)
