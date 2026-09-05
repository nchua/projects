"""
Coach schemas (ARISE v3 spec §8.4 output contract, §15.5 ``DebriefResponse``).

Two families of models live here:

* ``DebriefModelOutput`` — the structured-output schema the model fills in.
  ``Adjustment`` is a discriminated union on ``op`` with the exact parameter
  names from spec §8.4; the engine's validators (``debrief_service``) run on
  top of it, so the model can only ever *propose* a typed op.
* ``DebriefResponse`` — the iOS contract (§15.5). Contract-mirror note: this
  is the canonical shape for the Swift ``DebriefResponse`` struct.
"""
from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.schemas.weekly_report import GoalProgressReport

Confidence = Literal["high", "medium", "low"]
Source = Literal["engine", "model"]
AdjustmentStatus = Literal["proposed", "accepted", "dismissed", "out_of_bounds"]
Decision = Literal["accept", "dismiss"]


# ---------------------------------------------------------------------------
# Model output (structured outputs schema)
# ---------------------------------------------------------------------------


class ModelConcern(BaseModel):
    """One narrated concern. ``flag`` must be an engine flag or ``other``."""
    flag: str = Field(description="An engine flag from context.candidates.concerns, or 'other'")
    text: str = Field(description="One or two terse sentences citing only context numbers")


class _AdjustmentBase(BaseModel):
    reason: str = Field(description="Why this op, citing only numbers present in the context")
    confidence: Confidence = "medium"
    source: Source = "model"


class SetProgressionOp(_AdjustmentBase):
    op: Literal["set_progression"]
    family: str = Field(description="A family_id from context.families")
    increment_lb: float = Field(description="Must equal that family's increment_lb")


class SetWeekMilesOp(_AdjustmentBase):
    op: Literal["set_week_miles"]
    week_start: str = Field(description="Monday of the week, YYYY-MM-DD")
    miles: float


class DeloadNowOp(_AdjustmentBase):
    op: Literal["deload_now"]
    scope: Literal["lifts", "runs", "all"]


class SwapDaysOp(_AdjustmentBase):
    op: Literal["swap_days"]
    a: str = Field(description="YYYY-MM-DD, a planned day next week")
    b: str = Field(description="YYYY-MM-DD, a planned day next week")


class ExtendArcOp(_AdjustmentBase):
    op: Literal["extend_arc"]
    weeks: int


class ChangeRepsOp(_AdjustmentBase):
    op: Literal["change_reps"]
    family: str = Field(description="A family_id from context.families")
    sets: int
    reps: List[int] = Field(description="[lo, hi] rep range")


class SetGoalDeadlineOp(_AdjustmentBase):
    op: Literal["set_goal_deadline"]
    goal_id: str
    deadline: str = Field(description="YYYY-MM-DD, later than the current deadline")


Adjustment = Annotated[
    Union[
        SetProgressionOp,
        SetWeekMilesOp,
        DeloadNowOp,
        SwapDaysOp,
        ExtendArcOp,
        ChangeRepsOp,
        SetGoalDeadlineOp,
    ],
    Field(discriminator="op"),
]

ADJUSTMENT_OPS = (
    "set_progression",
    "set_week_miles",
    "deload_now",
    "swap_days",
    "extend_arc",
    "change_reps",
    "set_goal_deadline",
)


class DebriefModelOutput(BaseModel):
    """Spec §8.4 output contract — what ``client.beta.messages.parse`` fills."""
    summary: str = Field(description="At most 4 sentences: what happened vs plan, the one thing that mattered")
    concerns: List[ModelConcern]
    adjustments: List[Adjustment] = Field(description="Ranked, at most 3")
    next_week_focus: str = Field(description="One line")


# ---------------------------------------------------------------------------
# API contract (§15.5)
# ---------------------------------------------------------------------------


class DebriefAdherence(BaseModel):
    planned: int
    done: int
    modified: int
    moved: int
    skipped: int


class DebriefHighlight(BaseModel):
    kind: str
    text: str


class DebriefConcern(BaseModel):
    flag: str
    text: str


class DebriefAdjustment(BaseModel):
    id: str
    op: str
    params: Dict[str, object]
    reason: str
    confidence: str
    source: str
    status: str            # proposed | accepted | dismissed | out_of_bounds
    validation_note: Optional[str] = None


class DebriefResponse(BaseModel):
    """GET /coach/debrief (spec §15.5)."""
    id: str
    week_start: str
    summary: str
    adherence: DebriefAdherence
    highlights: List[DebriefHighlight]
    concerns: List[DebriefConcern]
    adjustments: List[DebriefAdjustment]
    next_week_focus: str
    goal_reports: List[GoalProgressReport]
    generated_at: str
    source: str            # model | engine_fallback


class AdjustmentDecisionRequest(BaseModel):
    """POST /coach/debrief/{id}/adjustments/{adj_id}."""
    decision: Decision
