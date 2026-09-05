"""
Goal schemas - strength PR goal requests and responses
"""
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Maximum active goals per user
MAX_ACTIVE_GOALS = 5


class GoalCreate(BaseModel):
    """Request to create a new objective (ARISE v3 §4.6).

    v2 clients send ``exercise_id + target_weight + deadline`` and get a
    strength objective; ``kind="run"`` objectives send ``target_miles`` +
    ``run_scope`` and either a ``deadline`` or ``by="arc_end"``.
    """
    exercise_id: Optional[str] = Field(None, description="ID of the exercise to set goal for")
    target_weight: Optional[float] = Field(None, gt=0, description="Target weight to lift")
    target_reps: int = Field(default=1, ge=1, le=20, description="Target reps (1 = true 1RM goal)")
    weight_unit: str = Field(default="lb", description="Weight unit (lb or kg)")
    deadline: Optional[date] = Field(None, description="Target date to achieve the goal")
    notes: Optional[str] = Field(None, max_length=500)
    # ── ARISE v3 objectives ──
    kind: str = Field(default="strength", pattern="^(strength|run)$")
    campaign_id: Optional[str] = None
    target_miles: Optional[float] = Field(None, gt=0)
    run_scope: Optional[str] = Field(None, pattern="^(long_run|weekly)$")
    by: Optional[str] = Field(None, pattern="^(arc_end|date)$")

    @model_validator(mode="after")
    def _shape_for_kind(self) -> "GoalCreate":
        if self.kind == "run":
            if self.target_miles is None or self.run_scope is None:
                raise ValueError("run objectives need target_miles and run_scope")
            if self.deadline is None and self.by != "arc_end":
                raise ValueError("run objectives need a deadline or by='arc_end'")
        else:
            if not self.exercise_id or self.target_weight is None:
                raise ValueError("strength objectives need exercise_id and target_weight")
            if self.deadline is None and self.by != "arc_end":
                raise ValueError("strength objectives need a deadline or by='arc_end'")
        return self


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
    """A user's objective (strength or run)"""
    id: str
    exercise_id: Optional[str] = None
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

    # ── ARISE v3 objectives (§4.6) ──
    kind: str = "strength"
    campaign_id: Optional[str] = None
    target_miles: Optional[float] = None
    run_scope: Optional[str] = None
    pace_status: Optional[str] = None
    deadline_extensions: int = 0

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
    kind: str = "strength"
    target_miles: Optional[float] = None
    run_scope: Optional[str] = None

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


# ============ Objective preview (ARISE v3 §4.6) ============

class GoalPreviewResponse(BaseModel):
    """POST /goals/preview — the pace preview shown before saving."""
    kind: str
    current_e1rm: Optional[float] = None
    target_e1rm: Optional[float] = None
    required_weekly_gain_lb: Optional[float] = None
    slope_6wk_lb: Optional[float] = None
    weeks_remaining: float
    deadline: str
    ambitious: bool = False
    pace_status: str = "on_track"
    # Run objectives: the arc ramp at the deadline vs the target.
    ramp_at_deadline: Optional[float] = None
    target_miles: Optional[float] = None
