"""
Read-only owner export for spreadsheet mirrors.

``GET /export/workouts`` returns the owner's sessions, sets, weekly volume,
PRs and bodyweight as flat tables. A Google Sheet pulls it on a timer
(``docs/sheet-export/Code.gs``) so assistants that can read Sheets but not the
database see current training data.

Auth is a dedicated static bearer token (``EXPORT_TOKEN``), not a user JWT: the
caller is an unattended script, and the token can only read this one endpoint
for the one account named by ``EXPORT_USER_EMAIL``. Unset → 503, like the
WHOOP endpoints.
"""
import hmac
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import unauthorized
from app.core.rate_limit import limiter
from app.core.utils import utcnow
from app.models.bodyweight import BodyweightEntry
from app.models.exercise import Exercise
from app.models.pr import PR
from app.models.user import User
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.schemas.export import (
    ExportBodyweightRow,
    ExportPRRow,
    ExportSessionRow,
    ExportSetRow,
    ExportWeeklyMuscleRow,
    ExportWeeklyVolumeRow,
    WorkoutExportResponse,
)
from app.services.prescription_service import session_local_day, set_weight_lb

router = APIRouter()

EXPORT_RATE_LIMIT = "30/hour"
# A short token is a guessable token; treat it as not configured.
MIN_TOKEN_LENGTH = 32
METERS_PER_MILE = 1609.344

_bearer = HTTPBearer(auto_error=False)


def require_export_token(credentials: Optional[HTTPAuthorizationCredentials]) -> None:
    """Gate on the static ``EXPORT_TOKEN`` (constant-time compare).

    Called from the endpoint body, not as a dependency, so the rate limit
    also counts rejected tokens.
    """
    expected = settings.EXPORT_TOKEN.strip()
    if len(expected) < MIN_TOKEN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Export is not configured",
        )
    supplied = credentials.credentials if credentials else ""
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise unauthorized("Invalid export token")


def _export_user(db: Session) -> User:
    """The one account the export serves."""
    email = (settings.EXPORT_USER_EMAIL or settings.ADMIN_BOOTSTRAP_EMAIL).strip().lower()
    user = None
    if email:
        user = (
            db.query(User)
            .filter(func.lower(User.email) == email, User.is_deleted.is_(False))
            .first()
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Export is not configured",
        )
    return user


def _week_start(day: date) -> date:
    """Monday of the week containing ``day``."""
    return day - timedelta(days=day.weekday())


@router.get("/workouts", response_model=WorkoutExportResponse)
@limiter.limit(EXPORT_RATE_LIMIT)
async def export_workouts(
    request: Request,
    days: int = Query(180, ge=1, le=3650, description="Days of history before today (UTC)"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> WorkoutExportResponse:
    """Flat training tables for the last ``days`` days."""
    require_export_token(credentials)
    user = _export_user(db)
    end = utcnow().date()
    start = end - timedelta(days=days)

    # Fetch a day wide on the instant column, then bucket by local day.
    sessions = (
        db.query(WorkoutSession)
        .options(
            selectinload(WorkoutSession.workout_exercises).selectinload(WorkoutExercise.sets),
            selectinload(WorkoutSession.workout_exercises)
            .selectinload(WorkoutExercise.exercise),
        )
        .filter(
            WorkoutSession.user_id == user.id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= datetime.combine(start - timedelta(days=1), time.min),
        )
        .order_by(WorkoutSession.date)
        .all()
    )

    session_rows: List[ExportSessionRow] = []
    set_rows: List[ExportSetRow] = []
    weekly: Dict[date, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    muscle: Dict[Tuple[date, str], Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for session in sessions:
        day = session_local_day(session)
        if day < start:
            continue
        week = _week_start(day)
        working_sets = total_reps = 0
        tonnage = 0.0
        for we in session.workout_exercises:
            exercise = we.exercise
            name = exercise.name if exercise else "Unknown"
            primary = exercise.primary_muscle if exercise else None
            for s in we.sets:
                weight_lb = set_weight_lb(s)
                volume = 0.0 if s.is_warmup else weight_lb * s.reps
                set_rows.append(ExportSetRow(
                    session_id=session.id,
                    day=day,
                    week_start=week,
                    exercise=name,
                    family=exercise.family_id if exercise else None,
                    primary_muscle=primary,
                    exercise_order=we.order_index,
                    set_number=s.set_number,
                    weight_lb=round(weight_lb, 2),
                    reps=s.reps,
                    is_warmup=s.is_warmup,
                    is_bodyweight=s.is_bodyweight,
                    rpe=s.rpe,
                    rir=s.rir,
                    e1rm=round(s.e1rm, 1) if s.e1rm else None,
                    volume_lb=round(volume, 1),
                ))
                if s.is_warmup:
                    continue
                working_sets += 1
                total_reps += s.reps
                tonnage += volume
                bucket = muscle[(week, primary or "unknown")]
                bucket["working_sets"] += 1
                bucket["total_reps"] += s.reps
                bucket["tonnage_lb"] += volume

        is_strength = bool(session.workout_exercises)
        miles = (
            session.distance_meters / METERS_PER_MILE
            if session.distance_meters else None
        )
        session_rows.append(ExportSessionRow(
            session_id=session.id,
            day=day,
            week_start=week,
            name=session.name,
            kind="strength" if is_strength else "cardio",
            activity_type=session.activity_type,
            duration_minutes=session.duration_minutes,
            session_rpe=session.session_rpe,
            exercises=len(session.workout_exercises),
            working_sets=working_sets,
            total_reps=total_reps,
            tonnage_lb=round(tonnage, 1),
            distance_miles=round(miles, 2) if miles is not None else None,
            avg_heart_rate=session.avg_heart_rate,
            peak_heart_rate=session.peak_heart_rate,
            strain=session.strain,
            hr_source=session.hr_source,
            training_load=session.training_load,
            notes=session.notes,
        ))
        totals = weekly[week]
        totals["strength_sessions" if is_strength else "cardio_sessions"] += 1
        totals["working_sets"] += working_sets
        totals["total_reps"] += total_reps
        totals["tonnage_lb"] += tonnage
        totals["cardio_miles"] += miles or 0.0

    weekly_rows = [
        ExportWeeklyVolumeRow(
            week_start=week,
            strength_sessions=int(t["strength_sessions"]),
            cardio_sessions=int(t["cardio_sessions"]),
            working_sets=int(t["working_sets"]),
            total_reps=int(t["total_reps"]),
            tonnage_lb=round(t["tonnage_lb"], 1),
            cardio_miles=round(t["cardio_miles"], 2),
        )
        for week, t in sorted(weekly.items())
    ]
    muscle_rows = [
        ExportWeeklyMuscleRow(
            week_start=week,
            primary_muscle=name,
            working_sets=int(t["working_sets"]),
            total_reps=int(t["total_reps"]),
            tonnage_lb=round(t["tonnage_lb"], 1),
        )
        for (week, name), t in sorted(muscle.items())
    ]

    # PRs carry the raw logged weight and the session's stored datetime; read
    # the lb weight and local day from the set's session instead, and drop PRs
    # whose session was soft-deleted. PRs with no linked set keep their own values.
    prs = (
        db.query(PR, Exercise.name, Set, WorkoutSession)
        .join(Exercise, Exercise.id == PR.exercise_id)
        .outerjoin(Set, Set.id == PR.set_id)
        .outerjoin(WorkoutExercise, WorkoutExercise.id == Set.workout_exercise_id)
        .outerjoin(WorkoutSession, WorkoutSession.id == WorkoutExercise.session_id)
        .filter(
            PR.user_id == user.id,
            PR.achieved_at >= datetime.combine(start - timedelta(days=1), time.min),
            WorkoutSession.deleted_at.is_(None),
        )
        .order_by(PR.achieved_at)
        .all()
    )
    pr_rows: List[ExportPRRow] = []
    for pr, name, set_row, pr_session in prs:
        day = session_local_day(pr_session) if pr_session else pr.achieved_at.date()
        if day < start:
            continue
        is_rep_pr = pr.weight is not None
        weight_lb = set_weight_lb(set_row) if set_row is not None and is_rep_pr else pr.weight
        pr_rows.append(ExportPRRow(
            day=day,
            exercise=name,
            pr_type=pr.pr_type.value,
            e1rm=round(pr.value, 1) if pr.value else None,
            weight_lb=round(weight_lb, 2) if weight_lb is not None else None,
            reps=pr.reps,
        ))

    bodyweight = (
        db.query(BodyweightEntry)
        .filter(BodyweightEntry.user_id == user.id, BodyweightEntry.date >= start)
        .order_by(BodyweightEntry.date)
        .all()
    )
    bodyweight_rows = [
        ExportBodyweightRow(day=b.date, weight_lb=round(b.weight_lb, 1), source=b.source)
        for b in bodyweight
    ]

    return WorkoutExportResponse(
        generated_at=utcnow(),
        start=start,
        end=end,
        sessions=session_rows,
        sets=set_rows,
        weekly_volume=weekly_rows,
        weekly_muscle_volume=muscle_rows,
        prs=pr_rows,
        bodyweight=bodyweight_rows,
    )
