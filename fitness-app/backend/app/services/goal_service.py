"""
Goal Service - Strength PR goals CRUD and progress tracking
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.utils import ensure_utc, to_iso8601_utc
from app.models.campaign import Campaign
from app.models.exercise import Exercise
from app.models.goal import Goal, GoalKind, GoalProgressSnapshot, GoalStatus
from app.models.pr import PR
from app.services.exercise_family_service import family_for_exercise

logger = logging.getLogger(__name__)

# Maximum number of active goals per user
MAX_ACTIVE_GOALS = 5


def get_today_utc() -> date:
    """Get today's date in UTC"""
    return datetime.now(timezone.utc).date()


def days_until(target_date: date) -> int:
    """Calculate days remaining until a target date"""
    today = get_today_utc()
    delta = target_date - today
    return max(0, delta.days)


def weeks_until(target_date: date) -> int:
    """Calculate weeks remaining until a target date"""
    return days_until(target_date) // 7


def calculate_e1rm(weight: float, reps: int) -> float:
    """
    Calculate estimated 1RM using Epley formula.
    e1RM = weight * (1 + reps/30)

    For 1 rep, e1RM equals the weight itself.
    """
    if reps <= 0 or weight <= 0:
        return 0
    if reps == 1:
        return weight
    return weight * (1 + reps / 30)


def create_goal(
    db: Session,
    user_id: str,
    exercise_id: Optional[str],
    target_weight: Optional[float],
    weight_unit: str,
    deadline: date,
    target_reps: int = 1,
    notes: Optional[str] = None,
    *,
    kind: str = GoalKind.STRENGTH.value,
    campaign_id: Optional[str] = None,
    target_miles: Optional[float] = None,
    run_scope: Optional[str] = None,
) -> Goal:
    """
    Create a new objective (ARISE v3 §4.6): a strength PR goal or a run goal.

    Args:
        db: Database session
        user_id: User ID
        exercise_id: Exercise to set goal for (None for run objectives)
        target_weight: Target weight to lift (ignored for run objectives)
        weight_unit: lb or kg
        deadline: Target date
        target_reps: Target reps (1 = true 1RM goal, higher = rep goal)
        notes: Optional notes
        kind: strength | run
        campaign_id: The campaign the objective lives under (nullable)
        target_miles: Run objective target (long run or weekly total)
        run_scope: long_run | weekly

    Returns:
        Created Goal object
    """
    starting_e1rm = None
    if kind == GoalKind.STRENGTH.value and exercise_id:
        # Get current e1RM for this exercise (starting point)
        current_pr = db.query(PR).filter(
            PR.user_id == user_id,
            PR.exercise_id == exercise_id
        ).order_by(PR.value.desc()).first()
        starting_e1rm = current_pr.value if current_pr else None

    goal = Goal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        exercise_id=exercise_id if kind == GoalKind.STRENGTH.value else None,
        campaign_id=campaign_id,
        kind=kind,
        target_miles=target_miles if kind == GoalKind.RUN.value else None,
        run_scope=run_scope if kind == GoalKind.RUN.value else None,
        target_weight=float(target_weight) if (kind == GoalKind.STRENGTH.value and target_weight) else 0.0,
        target_reps=target_reps,
        weight_unit=weight_unit,
        deadline=deadline,
        starting_e1rm=starting_e1rm,
        current_e1rm=starting_e1rm,
        status=GoalStatus.ACTIVE.value,
        notes=notes
    )

    db.add(goal)
    db.flush()
    return goal


def get_user_goals(db: Session, user_id: str, include_inactive: bool = False) -> List[Goal]:
    """Get all goals for a user"""
    query = db.query(Goal).options(
        joinedload(Goal.exercise)
    ).filter(Goal.user_id == user_id)

    if not include_inactive:
        query = query.filter(Goal.status == GoalStatus.ACTIVE.value)

    return query.order_by(Goal.created_at.desc()).all()


def get_goal_by_id(db: Session, user_id: str, goal_id: str) -> Optional[Goal]:
    """Get a specific goal with exercise loaded"""
    return db.query(Goal).options(
        joinedload(Goal.exercise)
    ).filter(
        Goal.id == goal_id,
        Goal.user_id == user_id
    ).first()


def update_goal(
    db: Session,
    goal: Goal,
    target_weight: Optional[float] = None,
    target_reps: Optional[int] = None,
    weight_unit: Optional[str] = None,
    deadline: Optional[date] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None
) -> Goal:
    """Update an existing goal"""
    if target_weight is not None:
        goal.target_weight = target_weight
    if target_reps is not None:
        goal.target_reps = target_reps
    if weight_unit is not None:
        goal.weight_unit = weight_unit
    if deadline is not None:
        goal.deadline = deadline
    if notes is not None:
        goal.notes = notes
    if status is not None:
        goal.status = status
        if status == GoalStatus.ABANDONED.value:
            goal.abandoned_at = datetime.now(timezone.utc)
        elif status == GoalStatus.COMPLETED.value:
            goal.achieved_at = datetime.now(timezone.utc)

    db.flush()
    return goal


def update_goal_progress(
    db: Session,
    user_id: str,
    exercise_id: str,
    new_e1rm: float,
    weight: Optional[float] = None,
    reps: Optional[int] = None,
    workout_id: Optional[str] = None
) -> List[str]:
    """
    Update progress on goals when a new e1RM is achieved.
    Records a progress snapshot for tracking historical progress.

    Args:
        db: Database session
        user_id: User ID
        exercise_id: Exercise that was performed
        new_e1rm: New estimated 1RM
        weight: Actual weight lifted (optional)
        reps: Actual reps performed (optional)
        workout_id: Source workout ID (optional)

    Returns:
        List of goal IDs that were completed
    """
    # Find active goals for this exercise
    goals = db.query(Goal).filter(
        Goal.user_id == user_id,
        Goal.exercise_id == exercise_id,
        Goal.status == GoalStatus.ACTIVE.value
    ).all()

    completed_goal_ids = []

    for goal in goals:
        # Always record snapshot for graph visibility (plateaus, regression)
        snapshot = GoalProgressSnapshot(
            id=str(uuid.uuid4()),
            goal_id=goal.id,
            recorded_at=datetime.now(timezone.utc),
            e1rm=new_e1rm,
            weight=weight,
            reps=reps,
            workout_id=workout_id
        )
        db.add(snapshot)

        # Only update current e1RM upward
        if goal.current_e1rm is None or new_e1rm > goal.current_e1rm:
            goal.current_e1rm = new_e1rm

        # Calculate target e1RM (accounts for target_reps)
        target_e1rm = calculate_e1rm(goal.target_weight, goal.target_reps)

        # Check if goal is achieved (compare e1RMs)
        if new_e1rm >= target_e1rm and goal.status == GoalStatus.ACTIVE.value:
            goal.status = GoalStatus.COMPLETED.value
            goal.achieved_at = datetime.now(timezone.utc)
            completed_goal_ids.append(goal.id)

    db.flush()
    return completed_goal_ids


def calculate_goal_progress(goal: Goal, db: Optional[Session] = None) -> Dict[str, Any]:
    """Calculate progress metrics for a goal (run objectives use the arc ramp)."""
    if (goal.kind or GoalKind.STRENGTH.value) == GoalKind.RUN.value:
        ramp = run_goal_pace(db, goal) if db is not None else {}
        return {
            "progress_percent": ramp.get("progress_percent", 0.0),
            "weight_to_go": round(max(0.0, float(goal.target_miles or 0) - float(ramp.get("ramp_now") or 0)), 1),
            "weeks_remaining": weeks_until(goal.deadline),
            "target_e1rm": float(goal.target_miles or 0),
            "pace_status": ramp.get("pace_status"),
        }
    current = goal.current_e1rm or goal.starting_e1rm or 0
    # Calculate target e1RM from weight and reps
    target_reps = goal.target_reps if goal.target_reps else 1
    target_e1rm = calculate_e1rm(goal.target_weight, target_reps)

    if target_e1rm > 0:
        progress_percent = min(100, (current / target_e1rm) * 100)
    else:
        progress_percent = 0

    # Weight to go is now in terms of e1RM
    e1rm_to_go = max(0, target_e1rm - current)

    return {
        "progress_percent": round(progress_percent, 1),
        "weight_to_go": round(e1rm_to_go, 1),  # Actually e1RM to go
        "weeks_remaining": weeks_until(goal.deadline),
        "target_e1rm": round(target_e1rm, 1)
    }


def _display_name(goal: Goal) -> str:
    if goal.exercise:
        return goal.exercise.name
    if (goal.kind or GoalKind.STRENGTH.value) == GoalKind.RUN.value:
        return "Long run" if goal.run_scope == "long_run" else "Weekly miles"
    return "Unknown"


def goal_to_response(goal: Goal, db: Optional[Session] = None) -> Dict[str, Any]:
    """Convert Goal model to response dict"""
    progress = calculate_goal_progress(goal, db=db)
    target_reps = goal.target_reps if goal.target_reps else 1

    return {
        "id": goal.id,
        "exercise_id": goal.exercise_id,
        "exercise_name": _display_name(goal),
        "target_weight": goal.target_weight,
        "target_reps": target_reps,
        "target_e1rm": progress["target_e1rm"],
        "weight_unit": goal.weight_unit,
        "deadline": goal.deadline.isoformat(),
        "starting_e1rm": goal.starting_e1rm,
        "current_e1rm": goal.current_e1rm,
        "status": goal.status,
        "notes": goal.notes,
        "created_at": to_iso8601_utc(goal.created_at),
        "kind": goal.kind or GoalKind.STRENGTH.value,
        "campaign_id": goal.campaign_id,
        "target_miles": goal.target_miles,
        "run_scope": goal.run_scope,
        "deadline_extensions": int(goal.deadline_extensions or 0),
        **progress
    }


def goal_to_summary(goal: Goal, db: Optional[Session] = None) -> Dict[str, Any]:
    """Convert Goal model to summary dict"""
    progress = calculate_goal_progress(goal, db=db)
    target_reps = goal.target_reps if goal.target_reps else 1

    return {
        "id": goal.id,
        "exercise_name": _display_name(goal),
        "target_weight": goal.target_weight,
        "target_reps": target_reps,
        "target_e1rm": progress["target_e1rm"],
        "weight_unit": goal.weight_unit,
        "deadline": goal.deadline.isoformat(),
        "progress_percent": progress["progress_percent"],
        "status": goal.status,
        "kind": goal.kind or GoalKind.STRENGTH.value,
        "target_miles": goal.target_miles,
        "run_scope": goal.run_scope,
    }


def get_goal_progress_data(db: Session, goal: Goal) -> Dict[str, Any]:
    """
    Get goal progress history with projected vs actual data for charting.

    Args:
        db: Database session
        goal: Goal with loaded exercise relationship

    Returns:
        Dict with actual_points, projected_points, status, and metrics
    """
    # Get progress snapshots ordered by date
    snapshots = db.query(GoalProgressSnapshot).filter(
        GoalProgressSnapshot.goal_id == goal.id
    ).order_by(GoalProgressSnapshot.recorded_at).all()

    # Build actual points from snapshots
    actual_points = []
    for snapshot in snapshots:
        actual_points.append({
            "date": snapshot.recorded_at.date().isoformat(),
            "e1rm": round(snapshot.e1rm, 1)
        })

    # If no snapshots but we have starting e1rm, add that as first point
    if not actual_points and goal.starting_e1rm:
        actual_points.append({
            "date": goal.created_at.date().isoformat(),
            "e1rm": round(goal.starting_e1rm, 1)
        })

    # Add current e1rm as most recent point if different from last snapshot
    if goal.current_e1rm:
        if not actual_points or actual_points[-1]["e1rm"] != round(goal.current_e1rm, 1):
            actual_points.append({
                "date": get_today_utc().isoformat(),
                "e1rm": round(goal.current_e1rm, 1)
            })

    # Calculate target e1RM
    target_reps = goal.target_reps if goal.target_reps else 1
    target_e1rm = calculate_e1rm(goal.target_weight, target_reps)

    # Build projected line (linear from start to target)
    start_date = goal.created_at.date()
    end_date = goal.deadline
    start_e1rm = goal.starting_e1rm or (goal.current_e1rm or target_e1rm * 0.85)

    projected_points = [
        {"date": start_date.isoformat(), "e1rm": round(start_e1rm, 1)},
        {"date": end_date.isoformat(), "e1rm": round(target_e1rm, 1)}
    ]

    # Calculate status and metrics
    today = get_today_utc()
    current_e1rm = goal.current_e1rm or start_e1rm
    total_days = (end_date - start_date).days
    days_elapsed = (today - start_date).days

    # Expected progress at this point (linear)
    if total_days > 0:
        expected_progress_pct = min(1.0, days_elapsed / total_days)
        expected_e1rm = start_e1rm + (target_e1rm - start_e1rm) * expected_progress_pct
    else:
        expected_e1rm = target_e1rm

    # Determine status
    if current_e1rm >= target_e1rm:
        status = "ahead"
        # Calculate how many weeks early we'd hit the target
        weeks_diff = max(0, weeks_until(end_date))
    elif current_e1rm >= expected_e1rm:
        # Check if significantly ahead (> 1 week)
        if current_e1rm >= expected_e1rm + 2.5:  # 2.5 lb buffer
            status = "ahead"
        else:
            status = "on_track"
        # Calculate weeks difference based on progress rate
        e1rm_gained = current_e1rm - start_e1rm
        if e1rm_gained > 0 and days_elapsed > 0:
            rate_per_day = e1rm_gained / days_elapsed
            if rate_per_day > 0:
                days_to_target = (target_e1rm - current_e1rm) / rate_per_day
                projected_end = today + timedelta(days=int(days_to_target))
                weeks_diff = (end_date - projected_end).days // 7
            else:
                weeks_diff = -weeks_until(end_date)
        else:
            weeks_diff = 0
    else:
        status = "behind"
        # Calculate how many weeks behind
        e1rm_behind = expected_e1rm - current_e1rm
        if total_days > 0:
            weekly_expected_gain = (target_e1rm - start_e1rm) / (total_days / 7)
            if weekly_expected_gain > 0:
                weeks_diff = -int(e1rm_behind / weekly_expected_gain)
            else:
                weeks_diff = 0
        else:
            weeks_diff = 0

    # Calculate weekly gain rates
    if days_elapsed >= 7:
        weeks_elapsed = days_elapsed / 7
        weekly_gain_rate = (current_e1rm - start_e1rm) / weeks_elapsed if weeks_elapsed > 0 else 0
    else:
        weekly_gain_rate = 0

    days_remaining = (end_date - today).days
    weeks_remaining = max(1, days_remaining / 7)
    e1rm_remaining = target_e1rm - current_e1rm
    required_gain_rate = e1rm_remaining / weeks_remaining if weeks_remaining > 0 else 0

    return {
        "goal_id": goal.id,
        "exercise_name": goal.exercise.name if goal.exercise else "Unknown",
        "target_weight": goal.target_weight,
        "target_reps": target_reps,
        "target_e1rm": round(target_e1rm, 1),
        "target_date": end_date.isoformat(),
        "starting_e1rm": goal.starting_e1rm,
        "current_e1rm": goal.current_e1rm,
        "weight_unit": goal.weight_unit,
        "actual_points": actual_points,
        "projected_points": projected_points,
        "status": status,
        "weeks_difference": weeks_diff,
        "weekly_gain_rate": round(weekly_gain_rate, 2),
        "required_gain_rate": round(required_gain_rate, 2)
    }


# ═══════════════════════════════════════════════════════════════════════════
# ARISE v3 §4.6 — Objectives under the Campaign
# ═══════════════════════════════════════════════════════════════════════════

MAX_DEADLINE_EXTENSION_DAYS = 28
AMBITIOUS_SLOPE_FACTOR = 2.0


def _active_campaign(db: Session, user_id: str) -> Optional[Campaign]:
    from app.services.campaign_service import get_active_campaign  # lazy: cycle
    return get_active_campaign(db, user_id)


def resolve_objective_deadline(db: Session, user_id: str, data: Any, campaign: Optional[Campaign]) -> date:
    """``by == "arc_end"`` → the current arc's last day; else the explicit deadline."""
    if getattr(data, "by", None) == "arc_end":
        from app.services.campaign_service import arc_bounds, week_context  # lazy: cycle
        campaign = campaign or _active_campaign(db, user_id)
        if campaign is None:
            raise ValueError("no active campaign — set an explicit deadline")
        ctx = week_context(campaign, max(get_today_utc(), campaign.start_date))
        if ctx is None:
            raise ValueError("the campaign has ended — set an explicit deadline")
        for arc, _start, end in arc_bounds(campaign):
            if arc.id == ctx["arc"].id:
                return end
    if data.deadline is None:
        raise ValueError("deadline required")
    return data.deadline


def create_objective(db: Session, user_id: str, data: Any, campaign: Optional[Campaign] = None) -> Goal:
    """Validate a ``GoalCreate`` and create it under the active campaign.

    Raises ``ValueError`` with a human message (the API maps it to 400).
    """
    campaign = campaign or _active_campaign(db, user_id)
    kind = data.kind or GoalKind.STRENGTH.value
    if kind == GoalKind.STRENGTH.value:
        exercise = db.query(Exercise).filter(Exercise.id == data.exercise_id).first()
        if exercise is None:
            raise ValueError("Exercise not found")
    deadline = resolve_objective_deadline(db, user_id, data, campaign)
    if deadline < get_today_utc():
        raise ValueError("deadline is in the past")
    return create_goal(
        db=db,
        user_id=user_id,
        exercise_id=data.exercise_id,
        target_weight=data.target_weight,
        weight_unit=data.weight_unit,
        deadline=deadline,
        target_reps=data.target_reps,
        notes=data.notes,
        kind=kind,
        campaign_id=data.campaign_id or (campaign.id if campaign else None),
        target_miles=data.target_miles,
        run_scope=data.run_scope,
    )


def family_for_goal(db: Session, goal: Goal) -> Optional[str]:
    if not goal.exercise_id:
        return None
    return family_for_exercise(db, goal.exercise_id)


def _family_exercise_ids(db: Session, goal: Goal, family_id: Optional[str]) -> List[str]:
    if family_id:
        ids = [r[0] for r in db.query(Exercise.id).filter(Exercise.family_id == family_id).all()]
        if goal.exercise_id and goal.exercise_id not in ids:
            ids.append(goal.exercise_id)
        return ids
    if goal.exercise_id:
        from app.services.pr_detection import get_canonical_exercise_ids
        return get_canonical_exercise_ids(db, goal.exercise_id)
    return []


def _weekly_gain_asof(snapshots: List[GoalProgressSnapshot], asof: datetime) -> Optional[float]:
    """Average weekly e1RM gain over the 4 weeks before ``asof`` (weekly_report math)."""
    rows = sorted((s for s in snapshots if ensure_utc(s.recorded_at) <= asof), key=lambda s: s.recorded_at)
    if len(rows) < 2:
        return None
    recent = [s for s in rows if ensure_utc(s.recorded_at) >= asof - timedelta(weeks=4)]
    if len(recent) < 2:
        recent = rows
    first, last = recent[0], recent[-1]
    days = (ensure_utc(last.recorded_at) - ensure_utc(first.recorded_at)).days
    if days <= 0:
        return None
    return (last.e1rm - first.e1rm) / (days / 7.0)


def strength_goal_pace(goal: Goal, asof: Optional[datetime] = None) -> Dict[str, Any]:
    """Pace of a strength objective as of a moment (default now), weekly-report math."""
    from app.services.weekly_report_service import _calculate_pace_status  # read-only reuse

    asof = asof or datetime.now(timezone.utc)
    snapshots = list(goal.progress_snapshots or [])
    starting = goal.starting_e1rm or 0
    seen = [s.e1rm for s in snapshots if ensure_utc(s.recorded_at) <= asof]
    current = max([starting, *seen]) if seen else (goal.current_e1rm or starting)
    target_e1rm = calculate_e1rm(goal.target_weight, goal.target_reps or 1)
    total = target_e1rm - starting if target_e1rm != starting else 1
    progress_pct = max(0.0, min(100.0, ((current - starting) / total) * 100))
    weeks_remaining = max((goal.deadline - asof.date()).days / 7.0, 0)
    required = round((target_e1rm - current) / weeks_remaining, 2) if weeks_remaining > 0 else None
    actual = _weekly_gain_asof(snapshots, asof)
    status = _calculate_pace_status(required, actual, progress_pct)
    return {
        "pace_status": status.value if hasattr(status, "value") else str(status),
        "required_weekly_gain": required,
        "actual_weekly_gain": round(actual, 2) if actual is not None else None,
        "current_e1rm": round(current, 1),
        "target_e1rm": round(target_e1rm, 1),
        "weeks_remaining": round(weeks_remaining, 1),
        "progress_percent": round(progress_pct, 1),
    }


def run_goal_pace(db: Session, goal: Goal, today: Optional[date] = None) -> Dict[str, Any]:
    """A run objective's pace is the arc ramp itself (spec §4.6)."""
    from app.services.campaign_service import (  # lazy: cycle
        get_campaign,
        long_run_miles_for_week,
        monday_of,
        week_target_miles,
    )

    today = today or get_today_utc()
    campaign = None
    if goal.campaign_id:
        campaign = get_campaign(db, goal.user_id, goal.campaign_id)
    campaign = campaign or _active_campaign(db, goal.user_id)
    target = float(goal.target_miles or 0)
    if campaign is None or target <= 0:
        return {"pace_status": "on_track", "progress_percent": 0.0, "ramp_now": None, "ramp_at_deadline": None}
    if goal.run_scope == "long_run":
        def ramp(c, ws, **kw):
            return long_run_miles_for_week(c, ws, **kw)
    else:
        def ramp(c, ws, **kw):
            return week_target_miles(db, c, ws, **kw)
    now_week = monday_of(max(today, campaign.start_date))
    ramp_now = ramp(campaign, now_week)
    # Judge the deadline by the ramp the plan *intends* there — the linear ramp
    # only reaches the arc's max on its last week, which is always a cutback.
    ramp_at_deadline = ramp(campaign, monday_of(goal.deadline), include_deload=False)
    if ramp_at_deadline is None or ramp_at_deadline + 1e-6 < target:
        status = "behind"
    elif ramp_now is not None and ramp_now + 1e-6 >= target:
        status = "ahead"
    else:
        status = "on_track"
    progress = min(100.0, (ramp_now or 0) / target * 100) if target else 0.0
    return {
        "pace_status": status,
        "progress_percent": round(progress, 1),
        "ramp_now": ramp_now,
        "ramp_at_deadline": ramp_at_deadline,
    }


def strength_goal_chips(db: Session, user_id: str) -> Dict[str, Dict[str, Any]]:
    """``{family_id: {goal_id, target_weight, target_reps, deadline, pace_status}}`` for active strength goals."""
    goals = (
        db.query(Goal)
        .options(joinedload(Goal.progress_snapshots))
        .filter(Goal.user_id == user_id, Goal.status == GoalStatus.ACTIVE.value,
                Goal.kind == GoalKind.STRENGTH.value)
        .all()
    )
    chips: Dict[str, Dict[str, Any]] = {}
    for goal in goals:
        fam = family_for_goal(db, goal)
        if not fam or fam in chips:
            continue
        pace = strength_goal_pace(goal)
        chips[fam] = {
            "goal_id": goal.id,
            "target_weight": goal.target_weight,
            "target_reps": goal.target_reps or 1,
            "deadline": goal.deadline.isoformat(),
            "pace_status": pace["pace_status"],
        }
    return chips


def active_strength_goal_families(db: Session, user_id: str) -> set:
    goals = db.query(Goal).filter(
        Goal.user_id == user_id, Goal.status == GoalStatus.ACTIVE.value,
        Goal.kind == GoalKind.STRENGTH.value,
    ).all()
    return {fam for fam in (family_for_goal(db, g) for g in goals) if fam}


def slope_for_family(db: Session, user_id: str, exercise_ids: List[str]) -> Optional[float]:
    from app.services.trend_service import weekly_best_e1rm_series, weekly_slope
    if not exercise_ids:
        return None
    return weekly_slope(weekly_best_e1rm_series(db, user_id, exercise_ids))


def goal_flags(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """Per active objective: pace, ``goal_behind`` (behind 2 weeks running), ``goal_ambitious``."""
    goals = (
        db.query(Goal)
        .options(joinedload(Goal.progress_snapshots), joinedload(Goal.exercise))
        .filter(Goal.user_id == user_id, Goal.status == GoalStatus.ACTIVE.value)
        .all()
    )
    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for goal in goals:
        fam = family_for_goal(db, goal)
        if (goal.kind or GoalKind.STRENGTH.value) == GoalKind.RUN.value:
            pace = run_goal_pace(db, goal)
            out.append({
                "goal_id": goal.id, "kind": goal.kind, "family_id": None, "exercise_id": None,
                "target_weight": None, "target_reps": None, "target_miles": goal.target_miles,
                "run_scope": goal.run_scope, "deadline": goal.deadline.isoformat(),
                "pace_status": pace["pace_status"],
                "goal_behind": pace["pace_status"] == "behind",
                "goal_ambitious": False,
                "required_weekly_gain": None, "actual_weekly_gain": None,
                "deadline_extensions": int(goal.deadline_extensions or 0),
            })
            continue
        now_pace = strength_goal_pace(goal, now)
        last_week = strength_goal_pace(goal, now - timedelta(days=7))
        slope = slope_for_family(db, user_id, _family_exercise_ids(db, goal, fam))
        required = now_pace["required_weekly_gain"]
        ambitious = bool(
            slope is not None and required is not None and required > 0
            and required > AMBITIOUS_SLOPE_FACTOR * max(slope, 0.0)
        )
        out.append({
            "goal_id": goal.id, "kind": GoalKind.STRENGTH.value, "family_id": fam,
            "exercise_id": goal.exercise_id, "target_weight": goal.target_weight,
            "target_reps": goal.target_reps or 1, "target_miles": None, "run_scope": None,
            "deadline": goal.deadline.isoformat(),
            "pace_status": now_pace["pace_status"],
            "goal_behind": now_pace["pace_status"] == "behind" and last_week["pace_status"] == "behind",
            "goal_ambitious": ambitious,
            "required_weekly_gain": required,
            "actual_weekly_gain": now_pace["actual_weekly_gain"],
            "slope_6wk_lb": slope,
            "deadline_extensions": int(goal.deadline_extensions or 0),
        })
    return out


def extend_goal_deadline(db: Session, user_id: str, goal_id: str, deadline: date) -> Goal:
    """``set_goal_deadline`` op: extend only, ≤ 4 weeks, once per objective."""
    goal = get_goal_by_id(db, user_id, goal_id)
    if goal is None:
        raise ValueError("objective not found")
    if goal.status != GoalStatus.ACTIVE.value:
        raise ValueError("only active objectives can be extended")
    if int(goal.deadline_extensions or 0) >= 1:
        raise ValueError("this objective has already been extended once")
    if deadline <= goal.deadline:
        raise ValueError("deadlines can only move later")
    if (deadline - goal.deadline).days > MAX_DEADLINE_EXTENSION_DAYS:
        raise ValueError("extend by at most 4 weeks")
    goal.deadline = deadline
    goal.deadline_extensions = int(goal.deadline_extensions or 0) + 1
    db.flush()
    return goal


def preview_goal(db: Session, user_id: str, data: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """POST /goals/preview — e1RM today, target e1RM, required lb/week vs the 6-week slope."""
    from app.services.prescription_service import best_recent_set  # anchor query reuse

    today = today or get_today_utc()
    campaign = _active_campaign(db, user_id)
    deadline = resolve_objective_deadline(db, user_id, data, campaign)
    weeks_remaining = max((deadline - today).days / 7.0, 0)
    if (data.kind or GoalKind.STRENGTH.value) == GoalKind.RUN.value:
        probe = Goal(
            user_id=user_id, kind=GoalKind.RUN.value, target_miles=data.target_miles,
            run_scope=data.run_scope, deadline=deadline, target_weight=0.0,
            campaign_id=campaign.id if campaign else None,
        )
        pace = run_goal_pace(db, probe, today)
        return {
            "kind": GoalKind.RUN.value, "current_e1rm": None, "target_e1rm": None,
            "required_weekly_gain_lb": None, "slope_6wk_lb": None,
            "weeks_remaining": round(weeks_remaining, 1), "deadline": deadline.isoformat(),
            "ambitious": pace["pace_status"] == "behind", "pace_status": pace["pace_status"],
            "ramp_at_deadline": pace["ramp_at_deadline"], "target_miles": data.target_miles,
        }
    exercise = db.query(Exercise).filter(Exercise.id == data.exercise_id).first()
    if exercise is None:
        raise ValueError("Exercise not found")
    fam = family_for_exercise(db, exercise.id)
    probe = Goal(user_id=user_id, exercise_id=exercise.id)
    ids = _family_exercise_ids(db, probe, fam)
    best = best_recent_set(db, user_id, ids, before=today + timedelta(days=1), days=90, max_reps=None)
    current = round(best[0].e1rm, 1) if best else None
    if current is None:
        pr = db.query(PR).filter(PR.user_id == user_id, PR.exercise_id.in_(ids)).order_by(PR.value.desc()).first()
        current = round(pr.value, 1) if pr else None
    target_e1rm = round(calculate_e1rm(data.target_weight, data.target_reps or 1), 1)
    required = None
    if current is not None and weeks_remaining > 0:
        required = round((target_e1rm - current) / weeks_remaining, 2)
    slope = slope_for_family(db, user_id, ids)
    ambitious = bool(
        slope is not None and required is not None and required > 0
        and required > AMBITIOUS_SLOPE_FACTOR * max(slope, 0.0)
    )
    if current is not None and current >= target_e1rm:
        pace = "ahead"
    elif required is None or slope is None:
        pace = "on_track"
    elif slope <= 0:
        pace = "behind"
    else:
        ratio = slope / required if required > 0 else 2.0
        pace = "ahead" if ratio >= 1.2 else ("on_track" if ratio >= 0.8 else "behind")
    return {
        "kind": GoalKind.STRENGTH.value, "current_e1rm": current, "target_e1rm": target_e1rm,
        "required_weekly_gain_lb": required, "slope_6wk_lb": slope,
        "weeks_remaining": round(weeks_remaining, 1), "deadline": deadline.isoformat(),
        "ambitious": ambitious, "pace_status": pace, "ramp_at_deadline": None, "target_miles": None,
    }
