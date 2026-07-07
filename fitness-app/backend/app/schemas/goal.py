"""
Goal schemas - strength PR goal requests and responses
"""
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# Maximum active goals per user
MAX_ACTIVE_GOALS = 5


class GoalCreate(BaseModel):
    """Request to create a new strength goal"""
    exercise_id: str = Field(..., description="ID of the exercise to set goal for")
    target_weight: float = Field(..., gt=0, description="Target weight to lift")
    target_reps: int = Field(default=1, ge=1, le=20, description="Target reps (1 = true 1RM goal)")
    weight_unit: str = Field(default="lb", description="Weight unit (lb or kg)")
    deadline: date = Field(..., description="Target date to achieve the goal")
    notes: Optional[str] = Field(None, max_length=500)


class GoalBatchCreate(BaseModel):
    """Request to create multiple strength goals at once (for wizard)"""
    goals: List[GoalCreate] = Field(..., min_length=1, max_length=MAX_ACTIVE_GOALS)

    @field_validator('goals')
    @classmethod
    def validate_goals_count(cls, v):
        if len(v) > MAX_ACTIVE_GOALS:
            raise ValueError(f'Maximum {MAX_ACTIVE_GOALS} goals allowed')
        return v


class GoalUpdate(BaseModel):
    """Request to update an existing goal"""
    target_weight: Optional[float] = Field(None, gt=0)
    target_reps: Optional[int] = Field(None, ge=1, le=20)
    weight_unit: Optional[str] = None
    deadline: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = None  # For abandoning a goal


class GoalResponse(BaseModel):
    """A user's strength goal"""
    id: str
    exercise_id: str
    exercise_name: str
    target_weight: float
    target_reps: int  # Target reps (1 = true 1RM goal)
    target_e1rm: float  # Calculated e1RM for target (weight * (1 + reps/30))
    weight_unit: str
    deadline: str  # ISO date string
    starting_e1rm: Optional[float]
    current_e1rm: Optional[float]
    status: str
    notes: Optional[str]
    created_at: str

    # Computed progress fields
    progress_percent: float  # 0-100
    weight_to_go: float  # Remaining e1RM to reach goal
    weeks_remaining: int

    class Config:
        from_attributes = True


class GoalSummaryResponse(BaseModel):
    """Compact goal info for lists"""
    id: str
    exercise_name: str
    target_weight: float
    target_reps: int  # Target reps (1 = true 1RM goal)
    target_e1rm: float  # Calculated e1RM for target
    weight_unit: str
    deadline: str
    progress_percent: float
    status: str

    class Config:
        from_attributes = True


class GoalsListResponse(BaseModel):
    """List of user's goals"""
    goals: List[GoalSummaryResponse]
    active_count: int
    completed_count: int
    can_add_more: bool = True  # True if user can add more goals (< 5 active)
    max_goals: int = MAX_ACTIVE_GOALS


class GoalBatchCreateResponse(BaseModel):
    """Response for batch goal creation"""
    goals: List[GoalResponse]
    created_count: int
    active_count: int  # Total active goals after creation


# ============ Goal Progress Schemas ============

class ProgressPoint(BaseModel):
    """A single point on the progress graph"""
    date: str  # ISO date string
    e1rm: float

    class Config:
        from_attributes = True


class GoalProgressResponse(BaseModel):
    """Goal progress history with projected vs actual data"""
    goal_id: str
    exercise_name: str
    target_weight: float
    target_reps: int
    target_e1rm: float
    target_date: str  # ISO date
    starting_e1rm: Optional[float]
    current_e1rm: Optional[float]
    weight_unit: str

    # Graph data
    actual_points: List[ProgressPoint]
    projected_points: List[ProgressPoint]

    # Status
    status: str  # "ahead", "on_track", "behind"
    weeks_difference: int  # positive = ahead, negative = behind
    weekly_gain_rate: float  # lbs per week based on actual progress
    required_gain_rate: float  # lbs per week needed to hit target

    class Config:
        from_attributes = True
