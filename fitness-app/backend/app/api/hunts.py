"""
Planned hunts API (ARISE v3 spec §4.5 / §15.3).

``GET /hunts/today`` is the fetch-time pipeline: materialize → load hunt →
Condition → guard flags (W2) → gate (W2) → ``prescribe`` → response. Nothing
is cached; readiness modulation is never persisted (only the guard's
rationale lines are appended to ``planned_hunts.rationale``, spec §6.4).
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.campaign import HuntType, PlannedHunt, PlannedHuntStatus
from app.models.user import User, UserProfile
from app.models.workout import WorkoutExercise, WorkoutSession
from app.schemas.hunt import HuntWeekResponse, PlannedHuntResponse, PlannedHuntUpdate
from app.services import campaign_service
from app.services.condition_service import compute_condition
from app.services.prescription_service import prescribe

router = APIRouter()

_FINISHED = {
    PlannedHuntStatus.DONE.value,
    PlannedHuntStatus.MODIFIED.value,
    PlannedHuntStatus.MOVED.value,
}


def _parse_date(value: Optional[str], field: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} must be YYYY-MM-DD"
        )


def _guard_flags(db: Session, user_id: str, local_date: date) -> List[str]:
    """W2's ``guard_flags_for_date`` — lazy import, neutral fallback ``[]``."""
    try:
        from app.services.training_load_service import guard_flags_for_date
    except ImportError:
        return []
    return list(guard_flags_for_date(db, user_id, local_date) or [])


def _gate_for(db: Session, user_id: str, hunt: PlannedHunt):
    """W2's ``gate_for_planned_hunt`` — lazy import, neutral fallback ``None``."""
    try:
        from app.services.gate_service import gate_for_planned_hunt
    except ImportError:
        return None
    return gate_for_planned_hunt(db, user_id, hunt)


def _load_session(db: Session, session_id: Optional[str]) -> Optional[WorkoutSession]:
    if not session_id:
        return None
    return (
        db.query(WorkoutSession)
        .options(joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets))
        .filter(WorkoutSession.id == session_id)
        .first()
    )


@router.get("/today", response_model=Optional[PlannedHuntResponse])
async def get_todays_hunt(
    client_date: Optional[str] = Query(None, description="Client's local date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Today's planned hunt with the prescription modulated *now*, or ``null`` on a rest day."""
    today = _parse_date(client_date, "client_date") or date.today()
    campaign_service.materialize_range(
        db, current_user.id, today, today + timedelta(days=campaign_service.MATERIALIZE_AHEAD_DAYS), today=today
    )
    hunt = campaign_service.hunt_on(db, current_user.id, today)
    if hunt is None:
        db.commit()
        return None
    if hunt.status != PlannedHuntStatus.PLANNED.value:
        db.commit()
        return campaign_service.hunt_to_dict(hunt, session=_load_session(db, hunt.session_id))

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    condition = compute_condition(db, current_user.id, today, profile.age if profile else None)
    guard_flags = _guard_flags(db, current_user.id, today)
    gate = _gate_for(db, current_user.id, hunt)
    prescription = prescribe(db, hunt, condition=condition, guard_flags=guard_flags, gate=gate)
    campaign_service.append_guard_rationale(hunt, prescription)
    db.commit()
    return campaign_service.hunt_to_dict(hunt, prescription=prescription)


@router.get("/week", response_model=HuntWeekResponse)
async def get_week(
    start: Optional[str] = Query(None, description="Any date in the week (YYYY-MM-DD)"),
    client_date: Optional[str] = Query(None, description="Client's local date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The week's planned hunts with linked session summaries + the pace strip."""
    today = _parse_date(client_date, "client_date") or date.today()
    week_start = campaign_service.monday_of(_parse_date(start, "start") or today)
    hunts = campaign_service.materialize_range(
        db, current_user.id, week_start,
        week_start + timedelta(days=campaign_service.MATERIALIZE_AHEAD_DAYS), today=today,
    )
    week_end = week_start + timedelta(days=6)
    week = [h for h in hunts if week_start <= h.date <= week_end]

    campaign = campaign_service.get_active_campaign(db, current_user.id)
    target = campaign_service.week_target_miles(db, campaign, week_start) if campaign else None
    ctx = campaign_service.week_context(campaign, max(week_start, campaign.start_date)) if campaign else None
    logged = campaign_service.logged_run_miles(db, current_user.id, week_start)
    lifts = [h for h in week if h.template and h.template.type == HuntType.LIFT.value]
    db.commit()
    return {
        "week_start": week_start.isoformat(),
        "hunts": [
            campaign_service.hunt_to_dict(h, session=_load_session(db, h.session_id)) for h in week
        ],
        "target_miles": target,
        "logged_miles": logged,
        "lifts_planned": len(lifts),
        "lifts_done": sum(1 for h in lifts if h.status in _FINISHED),
        "pace_status": campaign_service.pace_status(logged, target, week_start, today),
        "campaign_week": ctx["campaign_week"] if ctx and ctx["week_start"] == week_start else None,
    }


@router.put("/{hunt_id}", response_model=PlannedHuntResponse)
async def update_hunt(
    hunt_id: str,
    body: PlannedHuntUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """``{status: skipped}`` · ``{moved_to: date}`` · ``{swap_with: id}``."""
    hunt = campaign_service._hunt_query(db, current_user.id).filter(PlannedHunt.id == hunt_id).first()
    if hunt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planned hunt not found")
    try:
        if body.status == PlannedHuntStatus.SKIPPED.value:
            campaign_service.skip_hunt(db, hunt)
        elif body.moved_to is not None:
            campaign_service.move_hunt(db, hunt, body.moved_to)
        else:
            other = campaign_service._hunt_query(db, current_user.id).filter(
                PlannedHunt.id == body.swap_with
            ).first()
            if other is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="swap_with hunt not found")
            campaign_service.swap_hunts(db, hunt, other)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    return campaign_service.hunt_to_dict(hunt, session=_load_session(db, hunt.session_id))
