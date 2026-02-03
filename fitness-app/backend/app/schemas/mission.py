"""
Mission schemas - Goals and weekly mission responses
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date, datetime


# Maximum active goals per user
MAX_ACTIVE_GOALS = 5


# ============ Goal Schemas ============

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


# ============ Exercise Prescription Schemas ============

class ExercisePrescriptionResponse(BaseModel):
    """A prescribed exercise within a workout"""
    id: str
    exercise_id: str
    exercise_name: str
    order_index: int
    sets: int
    reps: int
    weight: Optional[float]
    weight_unit: str
    rpe_target: Optional[int]
    notes: Optional[str]
    is_completed: bool

    class Config:
        from_attributes = True


# ============ Mission Workout Schemas ============

class MissionWorkoutResponse(BaseModel):
    """A prescribed workout within a weekly mission"""
    id: str
    day_number: int
    focus: str
    primary_lift: Optional[str]
    status: str
    completed_workout_id: Optional[str]
    completed_at: Optional[str]
    prescriptions: List[ExercisePrescriptionResponse]

    class Config:
        from_attributes = True


class MissionWorkoutSummary(BaseModel):
    """Compact workout info for mission card"""
    id: str
    day_number: int
    focus: str
    status: str
    exercise_count: int

    class Config:
        from_attributes = True


# ============ Weekly Mission Schemas ============

class WeeklyMissionResponse(BaseModel):
    """Full weekly mission details"""
    id: str
    goal_id: Optional[str] = None  # Legacy: primary goal (nullable for multi-goal)
    goal_exercise_name: str
    goal_target_weight: float
    goal_weight_unit: str
    training_split: Optional[str] = None  # e.g., "ppl", "upper_lower"
    goals: List[GoalSummaryResponse] = []  # All goals in this mission
    goal_count: int = 1  # Number of goals
    week_start: str  # ISO date
    week_end: str    # ISO date
    status: str
    xp_reward: int
    weekly_target: Optional[str]
    coaching_message: Optional[str]
    workouts: List[MissionWorkoutResponse]

    # Computed fields
    workouts_completed: int
    workouts_total: int
    days_remaining: int

    class Config:
        from_attributes = True


class WeeklyMissionSummary(BaseModel):
    """Compact mission info for home card"""
    id: str
    goal_exercise_name: str
    goal_target_weight: float
    goal_weight_unit: str
    training_split: Optional[str] = None  # e.g., "ppl", "upper_lower"
    goals: List[GoalSummaryResponse] = []  # All goals in this mission
    goal_count: int = 1  # Number of goals
    status: str
    week_start: str
    week_end: str
    xp_reward: int
    workouts_completed: int
    workouts_total: int
    days_remaining: int
    workouts: List[MissionWorkoutSummary]

    class Config:
        from_attributes = True


class CurrentMissionResponse(BaseModel):
    """Response for GET /missions/current"""
    has_active_goal: bool  # Legacy: True if any active goals
    has_active_goals: bool = False  # True if any active goals
    goal: Optional[GoalSummaryResponse] = None  # Legacy: primary goal
    goals: List[GoalSummaryResponse] = []  # All active goals
    mission: Optional[WeeklyMissionSummary] = None
    needs_goal_setup: bool  # True if user has no active goals
    can_add_more_goals: bool = True  # True if < 5 active goals


class MissionAcceptResponse(BaseModel):
    """Response after accepting a mission"""
    success: bool
    mission: WeeklyMissionResponse
    message: str


class MissionDeclineResponse(BaseModel):
    """Response after declining a mission"""
    success: bool
    message: str


class MissionHistoryResponse(BaseModel):
    """Past missions"""
    missions: List[WeeklyMissionSummary]
    total_completed: int
    total_xp_earned: int
