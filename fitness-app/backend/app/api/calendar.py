"""
Weekly training-calendar aggregation for the training-calendar PWA.

`GET /calendar/weekly` returns the last N client-local weeks (Monday-start)
of training: lift sessions with their exercises/sets (weight x reps, e1RM)
and runs/cardio with distance + duration. The PWA overlays these actuals on
the planned schedule and computes on-pace reports client-side.

Sessions with a real time-of-day (HealthKit/watch imports) are stored
naive-UTC; the client passes `tz_offset_minutes` (JavaScript
`new Date().getTimezoneOffset()`, e.g. 420 for PDT) so those bucket on the
user's local calendar. Sessions stored at exactly midnight (manual and
screenshot logs) already mean "this local calendar day" and are bucketed
as-is — the same midnight convention as `to_iso8601_utc`.
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.workout import WorkoutExercise, WorkoutSession
from app.schemas.calendar import (
    CalendarExercise,
    CalendarLift,
    CalendarRun,
    CalendarSet,
    CalendarWeek,
    CalendarWeeklyResponse,
)

router = APIRouter()

METERS_PER_MILE = 1609.344

# Activity types that count toward weekly running mileage. Matches the
# controlled vocab from the HealthKit import ("Outdoor Run", "Indoor Run",
# "Running") case-insensitively.
_RUN_KEYWORDS = ("run", "running", "jog")


def _is_run(activity_type: Optional[str]) -> bool:
    if not activity_type:
        return False
    lowered = activity_type.lower()
    return any(k in lowered for k in _RUN_KEYWORDS)


@router.get("/weekly", response_model=CalendarWeeklyResponse)
async def get_weekly_calendar(
    weeks: int = Query(default=4, ge=1, le=26, description="How many weeks back (incl. current)"),
    tz_offset_minutes: int = Query(
        default=0,
        ge=-900,
        le=900,
        description="JS getTimezoneOffset(): minutes to SUBTRACT from local to get UTC "
                    "(e.g. 420 for UTC-7). local = utc - offset.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offset = timedelta(minutes=tz_offset_minutes)
    local_now = datetime.now(timezone.utc).replace(tzinfo=None) - offset
    current_monday: date = local_now.date() - timedelta(days=local_now.weekday())
    window_start_local: date = current_monday - timedelta(weeks=weeks - 1)

    # Query with a 1-day pad on each side so timezone shifting never drops a
    # session at the window edges; precise bucketing happens below.
    query_start = datetime.combine(window_start_local, datetime.min.time()) - timedelta(days=1)
    sessions = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises)
            .joinedload(WorkoutExercise.exercise),
            joinedload(WorkoutSession.workout_exercises)
            .joinedload(WorkoutExercise.sets),
        )
        .filter(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= query_start,
        )
        .order_by(WorkoutSession.date.asc())
        .all()
    )

    # Monday -> bucket
    buckets: dict[date, dict] = {
        window_start_local + timedelta(weeks=i): {"lifts": [], "runs": []}
        for i in range(weeks)
    }

    for s in sessions:
        # local_date is authoritative when present (stamped at logging /
        # import time). Legacy rows without it fall back to the dual storage
        # convention on `date` (see to_iso8601_utc): midnight means "this
        # local calendar day" (manual/screenshot logs — no shift), anything
        # else is a real UTC instant that needs the tz shift.
        if s.local_date is not None:
            local_day: date = s.local_date
        elif s.date.time() == time.min:
            local_day = s.date.date()
        else:
            local_day = (s.date - offset).date()
        monday = local_day - timedelta(days=local_day.weekday())
        bucket = buckets.get(monday)
        if bucket is None:
            continue  # outside the padded window after tz shift

        total_sets = sum(len(we.sets) for we in s.workout_exercises)
        if total_sets > 0:
            exercises: List[CalendarExercise] = []
            for we in s.workout_exercises:
                if not we.sets:
                    continue
                sets = [
                    CalendarSet(
                        weight=st.weight,
                        weight_unit=st.weight_unit.value if st.weight_unit else "lb",
                        reps=st.reps,
                        e1rm=st.e1rm,
                    )
                    for st in we.sets
                ]
                e1rms = [st.e1rm for st in we.sets if st.e1rm is not None]
                exercises.append(CalendarExercise(
                    name=we.exercise.name if we.exercise else "Unknown",
                    sets=sets,
                    top_weight=max((st.weight for st in we.sets), default=None),
                    best_e1rm=max(e1rms) if e1rms else None,
                ))
            bucket["lifts"].append(CalendarLift(
                id=s.id,
                local_date=local_day.isoformat(),
                day_index=local_day.weekday(),
                name=s.name,
                duration_minutes=s.duration_minutes,
                total_sets=total_sets,
                exercises=exercises,
            ))
        else:
            activity = s.activity_type
            # Cardio session: needs an activity type or a distance to be
            # meaningful on the calendar; plain empty sessions are skipped.
            if activity is None and s.distance_meters is None:
                continue
            miles = (
                round(s.distance_meters / METERS_PER_MILE, 2)
                if s.distance_meters is not None else None
            )
            # Prefer exact seconds; fall back to rounded minutes for legacy
            # rows so older runs still get an approximate pace.
            secs = s.duration_seconds or (
                s.duration_minutes * 60 if s.duration_minutes else None
            )
            pace = (
                round(secs / (s.distance_meters / METERS_PER_MILE))
                if secs and s.distance_meters and s.distance_meters >= 400
                else None
            )
            bucket["runs"].append(CalendarRun(
                id=s.id,
                local_date=local_day.isoformat(),
                day_index=local_day.weekday(),
                activity_type=activity,
                is_run=_is_run(activity) or (activity is None and s.distance_meters is not None),
                distance_miles=miles,
                duration_minutes=s.duration_minutes,
                duration_seconds=s.duration_seconds,
                pace_sec_per_mile=pace,
                avg_heart_rate=s.avg_heart_rate,
            ))

    week_list: List[CalendarWeek] = []
    for monday in sorted(buckets):
        b = buckets[monday]
        week_list.append(CalendarWeek(
            week_start=monday.isoformat(),
            lifts=b["lifts"],
            runs=b["runs"],
            run_miles=round(
                sum(r.distance_miles or 0.0 for r in b["runs"] if r.is_run), 2
            ),
            lift_sessions=len(b["lifts"]),
            total_sets=sum(lift.total_sets for lift in b["lifts"]),
        ))

    return CalendarWeeklyResponse(weeks=week_list)
