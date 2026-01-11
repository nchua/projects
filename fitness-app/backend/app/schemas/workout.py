"""
Workout schemas for request/response validation
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Union
from datetime import datetime
from app.models.workout import WeightUnit


class SetCreate(BaseModel):
    """Schema for creating a set"""
    weight: float = Field(..., ge=0, description="Weight lifted (0 for bodyweight exercises)")
    weight_unit: WeightUnit = Field(default=WeightUnit.LB, description="Weight unit (lb or kg)")
    reps: int = Field(..., gt=0, le=100, description="Number of reps")
    rpe: Optional[int] = Field(None, ge=1, le=10, description="Rate of Perceived Exertion (1-10)")
    rir: Optional[int] = Field(None, ge=0, le=5, description="Reps in Reserve (0-5)")
    set_number: int = Field(..., ge=1, description="Set number/order")


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
    created_at: str

    class Config:
        from_attributes = True


class WorkoutExerciseCreate(BaseModel):
    """Schema for creating an exercise within a workout"""
    exercise_id: str = Field(..., description="Exercise ID from library")
    order_index: int = Field(..., ge=0, description="Order of exercise in workout")
    sets: List[SetCreate] = Field(..., min_length=1, description="Sets for this exercise")


class WorkoutExerciseResponse(BaseModel):
    """Schema for workout exercise in responses"""
    id: str
    exercise_id: str
    exercise_name: str
    order_index: int
    sets: List[SetResponse]
    created_at: str

    class Config:
        from_attributes = True


class WorkoutCreate(BaseModel):
    """Schema for creating a workout"""
    date: Union[datetime, str] = Field(default_factory=datetime.utcnow, description="Workout date/time")
    duration_minutes: Optional[int] = Field(None, ge=1, le=600, description="Workout duration in minutes")
    session_rpe: Optional[int] = Field(None, ge=1, le=10, description="Overall session RPE")
    notes: Optional[str] = Field(None, max_length=1000, description="Workout notes")
    exercises: List[WorkoutExerciseCreate] = Field(..., min_length=1, description="Exercises in workout")

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
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
