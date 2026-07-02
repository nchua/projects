"""
Workout schemas for request/response validation
"""
from datetime import datetime, timezone
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator

from app.models.workout import WeightUnit


class SetCreate(BaseModel):
    """Schema for creating a set"""
    weight: float = Field(..., ge=0, description="Weight lifted (0 for bodyweight exercises)")
    weight_unit: WeightUnit = Field(default=WeightUnit.LB, description="Weight unit (lb or kg)")
    reps: int = Field(..., gt=0, le=100, description="Number of reps")
    rpe: Optional[int] = Field(None, ge=1, le=10, description="Rate of Perceived Exertion (1-10)")
    rir: Optional[int] = Field(None, ge=0, le=5, description="Reps in Reserve (0-5)")
    set_number: int = Field(..., ge=1, description="Set number/order")
    # Wearable timing + HR (Apple Watch records boundaries live; WHOOP backfill
    # may infer them). All optional so existing clients are unaffected.
    start_time: Optional[datetime] = Field(None, description="Set start time (UTC)")
    end_time: Optional[datetime] = Field(None, description="Set end time (UTC)")
    avg_heart_rate: Optional[int] = Field(None, ge=20, le=250, description="Avg BPM during set")
    peak_heart_rate: Optional[int] = Field(None, ge=20, le=250, description="Peak BPM during set")


class SetResponse(BaseModel):
    """Schema for set information in responses"""
    id: str
    weight: float
    weight_unit: str
    reps: int
    rpe: Optional[int]
    rir: Optional[int]
    set_number: int
    e1rm: Optional[float]
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    avg_heart_rate: Optional[int] = None
    peak_heart_rate: Optional[int] = None
    created_at: str

    class Config:
        from_attributes = True


class HeartRateSampleCreate(BaseModel):
    """A single raw HR sample sent with a workout (from Watch or WHOOP).

    Samples are attributed to a specific set server-side by timestamp window
    (matched against each set's start_time/end_time), not by index, since
    set_number is only unique within an exercise.
    """
    timestamp: datetime = Field(..., description="Sample time (UTC)")
    bpm: int = Field(..., ge=20, le=250, description="Heart rate in BPM")


class WorkoutExerciseCreate(BaseModel):
    """Schema for creating an exercise within a workout"""
    exercise_id: str = Field(..., description="Exercise ID from library")
    order_index: int = Field(..., ge=0, description="Order of exercise in workout")
    sets: List[SetCreate] = Field(..., min_length=1, description="Sets for this exercise")
    superset_group_id: Optional[str] = Field(None, description="Group ID for superset exercises")


class WorkoutExerciseResponse(BaseModel):
    """Schema for workout exercise in responses"""
    id: str
    exercise_id: str
    exercise_name: str
    order_index: int
    sets: List[SetResponse]
    superset_group_id: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class WorkoutCreate(BaseModel):
    """Schema for creating a workout"""
    date: Union[datetime, str] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Workout date/time")
    duration_minutes: Optional[int] = Field(None, ge=1, le=600, description="Workout duration in minutes")
    session_rpe: Optional[int] = Field(None, ge=1, le=10, description="Overall session RPE")
    notes: Optional[str] = Field(None, max_length=1000, description="Workout notes")
    exercises: List[WorkoutExerciseCreate] = Field(..., min_length=1, description="Exercises in workout")
    # ── Wearable HR (from Apple Watch live session; WHOOP backfills via its own
    # endpoint). All optional. Session summary fields are stored as-is; raw
    # samples are persisted and attributed to sets by timestamp window. ──
    avg_heart_rate: Optional[int] = Field(None, ge=20, le=250, description="Avg session BPM")
    peak_heart_rate: Optional[int] = Field(None, ge=20, le=250, description="Peak session BPM")
    strain: Optional[float] = Field(None, ge=0, le=21, description="WHOOP strain 0-21")
    kilojoules: Optional[float] = Field(None, ge=0, description="Energy expenditure (kJ)")
    hr_zone_seconds: Optional[dict] = Field(None, description="Seconds per HR zone, e.g. {\"z2\": 540}")
    hr_source: Optional[str] = Field(None, description="apple_watch | whoop | screenshot")
    heart_rate_samples: Optional[List[HeartRateSampleCreate]] = Field(
        None, description="Raw HR series for the session (attributed to sets server-side)"
    )
    # Optional client-generated idempotency key. iOS offline queue stamps one
    # per enqueued workout; if the same key re-arrives (e.g. network blip that
    # actually succeeded server-side), we return the existing row instead of
    # creating a duplicate. Format: any string up to 128 chars — UUID is the
    # expected shape but we don't enforce it.
    client_id: Optional[str] = Field(None, min_length=1, max_length=128, description="Client idempotency key")

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        """Parse date from various formats (date-only string, full ISO datetime, or datetime object)"""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # Try parsing date-only format first (e.g., "2026-01-09")
            try:
                return datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                pass
            # Try ISO format with time (e.g., "2026-01-09T10:30:00")
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                pass
        raise ValueError(f"Cannot parse date: {v}")


class WorkoutResponse(BaseModel):
    """Schema for workout information in responses"""
    id: str
    user_id: str
    date: str
    duration_minutes: Optional[int]
    session_rpe: Optional[int]
    notes: Optional[str]
    exercises: List[WorkoutExerciseResponse]
    avg_heart_rate: Optional[int] = None
    peak_heart_rate: Optional[int] = None
    strain: Optional[float] = None
    kilojoules: Optional[float] = None
    hr_zone_seconds: Optional[dict] = None
    hr_source: Optional[str] = None
    # 0-21 exertion score derived from hr_zone_seconds (Apple-Watch strain proxy).
    # None when no zone data; clients fall back to WHOOP strain.
    exertion_score: Optional[float] = None
    # Activity classification (mirrors WorkoutSummary) so the detail screen can
    # render a cardio session as an activity rather than a 0-set "quest".
    is_activity: bool = False
    activity_type: Optional[str] = None
    calories: Optional[int] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class XPBreakdown(BaseModel):
    """XP breakdown for workout"""
    workout_complete: int = 0
    volume_bonus: int = 0
    big_three_bonus: int = 0
    pr_bonus: int = 0
    streak_bonus: int = 0


class AchievementUnlocked(BaseModel):
    """Achievement unlocked during workout"""
    id: str
    name: str
    description: str
    icon: str
    xp_reward: int
    rarity: str


class PRAchieved(BaseModel):
    """PR achieved during workout"""
    exercise_name: str
    pr_type: str  # "e1rm" or "rep_pr"
    value: str    # "225 lb" or "315 lb x 5"
    xp_earned: int = 100  # XP bonus per PR


class DungeonSpawnedResponse(BaseModel):
    """Dungeon that spawned after workout"""
    id: str
    dungeon_id: str
    name: str
    rank: str
    base_xp_reward: int
    is_stretch_dungeon: bool
    stretch_bonus_percent: Optional[int] = None
    time_remaining_seconds: int
    message: str
    is_rare_gate: bool = False


class DungeonProgressResponse(BaseModel):
    """Dungeon progress made during workout"""
    dungeons_progressed: List[str] = []  # Dungeon IDs
    dungeons_completed: List[str] = []  # Dungeon IDs now ready to claim
    objectives_completed: List[str] = []  # Objective names


class WorkoutCreateResponse(BaseModel):
    """Response for workout creation including XP info"""
    workout: WorkoutResponse
    xp_earned: int
    xp_breakdown: dict
    total_xp: int
    level: int
    leveled_up: bool
    new_level: Optional[int] = None
    rank: str
    rank_changed: bool
    new_rank: Optional[str] = None
    current_streak: int
    achievements_unlocked: List[AchievementUnlocked] = []
    prs_achieved: List[PRAchieved] = []
    # Dungeon system
    dungeon_spawned: Optional[DungeonSpawnedResponse] = None
    dungeon_progress: Optional[DungeonProgressResponse] = None

    class Config:
        from_attributes = True


class WorkoutUpdate(BaseModel):
    """Schema for updating a workout"""
    date: Optional[Union[datetime, str]] = Field(None, description="Workout date/time")
    duration_minutes: Optional[int] = Field(None, ge=1, le=600, description="Workout duration in minutes")
    session_rpe: Optional[int] = Field(None, ge=1, le=10, description="Overall session RPE")
    notes: Optional[str] = Field(None, max_length=1000, description="Workout notes")
    exercises: Optional[List[WorkoutExerciseCreate]] = Field(None, min_length=1, description="Exercises in workout")

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        """Parse date from various formats"""
        if v is None:
            return v
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                pass
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                pass
        raise ValueError(f"Cannot parse date: {v}")


class WorkoutSummary(BaseModel):
    """Schema for workout summary (list view)"""
    id: str
    user_id: str
    date: str
    duration_minutes: Optional[int]
    session_rpe: Optional[int]
    notes: Optional[str]
    exercise_count: int
    total_sets: int
    exercise_names: List[str] = []
    primary_muscles: List[str] = []
    created_at: str
    updated_at: str
    # WHOOP activity fields (parsed from notes)
    is_whoop_activity: bool = False
    activity_type: Optional[str] = None
    strain: Optional[float] = None
    calories: Optional[int] = None
    # True for any pure cardio/sport session (WHOOP or Apple Watch) — i.e. a
    # set-less activity with a known activity_type. Drives the History row's
    # "activity" rendering regardless of data source.
    is_activity: bool = False
    # 0-21 exertion score derived from hr_zone_seconds (Apple-Watch strain proxy).
    exertion_score: Optional[float] = None
    # Wearable HR summary for the History-row provenance badge + biometrics.
    # Optional so rows without a wearable (and legacy data) render unchanged.
    avg_heart_rate: Optional[int] = None
    peak_heart_rate: Optional[int] = None
    hr_source: Optional[str] = None

    class Config:
        from_attributes = True
