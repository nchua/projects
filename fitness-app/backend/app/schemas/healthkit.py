"""
HealthKit (Apple Watch) workout import schemas for the
`POST /workouts/import-healthkit` endpoint.

The iOS app reads completed `HKWorkout`s + their raw HR series on-device,
maps `HKWorkoutActivityType` to a controlled `activity_type` vocabulary,
decimates samples, and batches them here. The backend dedups by HealthKit
UUID, routes cardio into synthetic sessions and strength into existing logged
sessions, and stamps `hr_source = "apple_watch"` server-side (so it is *not*
part of the request).

These schemas are the canonical contract for Chunk A; the Swift mirror structs
(Chunk B) and the iOS query builder (Chunk C) follow them field-for-field.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.workout import HeartRateSampleCreate


class HealthKitWorkout(BaseModel):
    """A single completed Apple-Watch workout to import.

    `start`/`end` accept ISO8601 UTC strings with a trailing ``Z`` and
    fractional seconds (the validator mirrors ``WorkoutCreate.parse_date``).
    `hr_source` is intentionally absent — the backend hard-stamps
    ``"apple_watch"``.
    """
    hk_uuid: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="HKWorkout.uuid.uuidString — dedup key",
    )
    activity_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Controlled vocab mapped from HKWorkoutActivityType on-device",
    )
    is_strength: bool = Field(
        default=False,
        description="Client declares strength vs cardio; backend routes on it",
    )
    start: datetime = Field(..., description="Workout start (ISO8601 UTC)")
    end: datetime = Field(..., description="Workout end (ISO8601 UTC); must be >= start")
    duration_seconds: int = Field(..., ge=1, description="Workout duration in seconds")
    kilojoules: Optional[float] = Field(
        None, ge=0, description="Energy expenditure (kJ); client converts kcal x 4.184"
    )
    avg_heart_rate: Optional[int] = Field(None, ge=20, le=250, description="Avg BPM")
    peak_heart_rate: Optional[int] = Field(None, ge=20, le=250, description="Peak BPM")
    hr_zone_seconds: Optional[dict[str, int]] = Field(
        None,
        description="Seconds per HR zone, e.g. {\"z1\": 120}; null when age unknown",
    )
    heart_rate_samples: Optional[list[HeartRateSampleCreate]] = Field(
        None, description="Raw HR series (reuses HeartRateSampleCreate shape)"
    )
    distance_meters: Optional[float] = Field(
        None, ge=0, description="Distance (m); v1 stores only in notes, may be null"
    )
    timezone_offset_minutes: Optional[int] = Field(
        None,
        ge=-14 * 60,
        le=14 * 60,
        description=(
            "User's UTC offset (minutes) at the workout's start, e.g. -420 for "
            "PDT. Used to bucket the created session on the user's local "
            "calendar day; when absent the session date falls back to UTC."
        ),
    )

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_date(cls, v):  # type: ignore[no-untyped-def]
        """Parse an ISO8601 datetime, accepting a trailing 'Z' and fractional seconds.

        Mirrors ``WorkoutCreate.parse_date`` so the import path accepts the same
        formats the rest of the codebase does. A datetime is returned as-is; a
        string is parsed via ``datetime.fromisoformat`` after normalizing ``Z``
        to ``+00:00`` (yielding a tz-aware value).
        """
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                pass
        raise ValueError(f"Cannot parse datetime: {v}")

    @model_validator(mode="after")
    def check_end_after_start(self) -> "HealthKitWorkout":
        """Ensure the workout's end is at or after its start."""
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


class HealthKitImportRequest(BaseModel):
    """Batch request wrapping the workouts to import (1..100 per call)."""
    workouts: list[HealthKitWorkout] = Field(..., min_length=1, max_length=100)


class HealthKitUnmatched(BaseModel):
    """A strength workout that had no overlapping logged session.

    Reported back (as an object, not a bare string) so the client can prompt
    the user to log the lift first; the ``hk_uuid`` is deliberately *not*
    consumed so a later re-import can attach once the session exists.
    """
    hk_uuid: str
    activity_type: str
    start: str
    end: str


class HealthKitImportResponse(BaseModel):
    """Result of an import batch.

    All lists are returned even when empty so the client can branch
    deterministically.
    """
    imported: list[str]
    skipped_duplicates: list[str]
    sessions_created: list[str]
    sessions_updated: list[str]
    unmatched: list[HealthKitUnmatched]
    quests_completed: list[str]
