"""
Planned-hunt Pydantic schemas (ARISE v3 spec §4.5 / §15.3).

Contract-mirror note: ``PlannedHuntResponse`` / ``PrescriptionResponse`` are
the canonical shapes the iOS ``PlannedHuntResponse`` struct in
APITypes.swift mirrors. Snake_case keys; every number comes from the
prescription engine (``prescription_service``), never from a model.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class PrescribedSet(BaseModel):
    """One target set. Warm-ups and the gate attempt are flagged, not typed."""
    set_number: int
    target_weight_lb: Optional[float] = None
    target_reps_lo: int
    target_reps_hi: int
    target_rpe: Optional[float] = None
    is_warmup: bool = False
    is_gate_attempt: bool = False


class GoalChip(BaseModel):
    """Objective chip on the Today's Hunt meta line (spec §4.6)."""
    goal_id: str
    target_weight: float
    target_reps: int
    deadline: str                      # YYYY-MM-DD
    pace_status: str                   # on_track | ahead | behind


class PrescribedExercise(BaseModel):
    family_id: str
    exercise_id: Optional[str] = None
    exercise_name: str
    role: str                          # main | secondary | accessory | gate | warmup
    alternatives: List[str] = Field(default_factory=list)   # exercise ids
    sets: List[PrescribedSet] = Field(default_factory=list)
    last_performance: Optional[str] = None
    progression_note: Optional[str] = None
    # ARISE v3 §4.6 goal chip — present only when the family has an active
    # strength objective. (Added by W1; the orchestrator mirrors it in Swift.)
    goal: Optional[GoalChip] = None


class PrescribedRun(BaseModel):
    kind: str                          # easy | long | shakeout
    miles: float
    hr_cap_bpm: int
    note: Optional[str] = None


class PrescriptionResponse(BaseModel):
    version: int
    exercises: List[PrescribedExercise] = Field(default_factory=list)
    run: Optional[PrescribedRun] = None
    notes: List[str] = Field(default_factory=list)


class RationaleLine(BaseModel):
    key: str
    text: str
    numbers: Dict[str, Any] = Field(default_factory=dict)


class Modulation(BaseModel):
    band: str
    factor: float
    note: str


class SessionSummary(BaseModel):
    """Linked session summary on the week view (spec §4.5)."""
    id: str
    name: Optional[str] = None
    local_date: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_sets: int = 0
    distance_miles: Optional[float] = None


class PlannedHuntResponse(BaseModel):
    """Spec §15.3 — exact keys."""
    id: str
    campaign_id: str
    arc_id: str
    template_id: str
    date: str                          # YYYY-MM-DD
    type: str                          # lift | run | light | rest
    title: str
    location_tag: Optional[str] = None
    status: str                        # planned | done | modified | skipped | moved
    session_id: Optional[str] = None
    moved_to: Optional[str] = None
    prescription: Optional[PrescriptionResponse] = None
    rationale: List[RationaleLine] = Field(default_factory=list)
    system_line: str = ""
    modulation: Optional[Modulation] = None
    guard_flags: List[str] = Field(default_factory=list)
    # Week view only: the linked session, when there is one.
    session_summary: Optional[SessionSummary] = None


class HuntWeekResponse(BaseModel):
    """GET /hunts/week — the Hunt tab week strip + pace strip."""
    week_start: str
    hunts: List[PlannedHuntResponse]
    target_miles: Optional[float] = None
    logged_miles: float = 0.0
    lifts_planned: int = 0
    lifts_done: int = 0
    pace_status: str = "on_pace"       # on_pace | behind | ahead
    campaign_week: Optional[int] = None


class PlannedHuntUpdate(BaseModel):
    """PUT /hunts/{id}: exactly one of status=skipped, moved_to, swap_with."""
    status: Optional[str] = None
    moved_to: Optional[date] = None
    swap_with: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "PlannedHuntUpdate":
        ops = [self.status is not None, self.moved_to is not None, self.swap_with is not None]
        if sum(ops) != 1:
            raise ValueError("send exactly one of status, moved_to, swap_with")
        if self.status is not None and self.status != "skipped":
            raise ValueError("status may only be set to 'skipped'")
        return self
