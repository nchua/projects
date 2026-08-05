"""
Weekly training-calendar schemas for the `GET /calendar/weekly` endpoint.

Read-only aggregation consumed by the training-calendar PWA
(https://nchua.github.io/projects/): per local week, the lift sessions
(exercises with sets x weight and best e1RM) and runs/cardio (distance,
duration, HR) plus weekly totals. Dates are bucketed into the *client's*
local days via the `tz_offset_minutes` query param (JS getTimezoneOffset()).
"""
from typing import List, Optional

from pydantic import BaseModel


class CalendarSet(BaseModel):
    weight: float
    weight_unit: str
    reps: int
    e1rm: Optional[float] = None


class CalendarExercise(BaseModel):
    name: str
    sets: List[CalendarSet]
    top_weight: Optional[float] = None   # heaviest set weight
    best_e1rm: Optional[float] = None    # best computed e1RM across sets


class CalendarLift(BaseModel):
    id: str
    local_date: str          # YYYY-MM-DD in the client's timezone
    day_index: int           # Monday=0 .. Sunday=6
    name: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_sets: int
    exercises: List[CalendarExercise]


class CalendarRun(BaseModel):
    id: str
    local_date: str
    day_index: int
    activity_type: Optional[str] = None
    is_run: bool             # True for run-like activities (vs other cardio)
    distance_miles: Optional[float] = None
    duration_minutes: Optional[int] = None
    avg_heart_rate: Optional[int] = None


class CalendarWeek(BaseModel):
    week_start: str          # Monday, YYYY-MM-DD (client-local)
    lifts: List[CalendarLift]
    runs: List[CalendarRun]
    run_miles: float         # sum of run distance for the week
    lift_sessions: int
    total_sets: int


class CalendarWeeklyResponse(BaseModel):
    weeks: List[CalendarWeek]   # oldest -> newest; last item is the current week
