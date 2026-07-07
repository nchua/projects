"""
Goal Service - Strength PR goals CRUD and progress tracking
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.utils import to_iso8601_utc
from app.models.goal import Goal, GoalProgressSnapshot, GoalStatus
from app.models.pr import PR

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
    exercise_id: str,
    target_weight: float,
    weight_unit: str,
    deadline: date,
    target_reps: int = 1,
    notes: Optional[str] = None
) -> Goal:
    """
    Create a new strength PR goal.

    Args:
        db: Database session
        user_id: User ID
        exercise_id: Exercise to set goal for
        target_weight: Target weight to lift
        weight_unit: lb or kg
        deadline: Target date
        target_reps: Target reps (1 = true 1RM goal, higher = rep goal)
        notes: Optional notes

    Returns:
        Created Goal object
    """
    # Get current e1RM for this exercise (starting point)
    current_pr = db.query(PR).filter(
        PR.user_id == user_id,
        PR.exercise_id == exercise_id
    ).order_by(PR.value.desc()).first()

    starting_e1rm = current_pr.value if current_pr else None

    goal = Goal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        exercise_id=exercise_id,
        target_weight=target_weight,
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


def calculate_goal_progress(goal: Goal) -> Dict[str, Any]:
    """Calculate progress metrics for a goal"""
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


def goal_to_response(goal: Goal) -> Dict[str, Any]:
    """Convert Goal model to response dict"""
    progress = calculate_goal_progress(goal)
    target_reps = goal.target_reps if goal.target_reps else 1

    return {
        "id": goal.id,
        "exercise_id": goal.exercise_id,
        "exercise_name": goal.exercise.name if goal.exercise else "Unknown",
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
        **progress
    }


def goal_to_summary(goal: Goal) -> Dict[str, Any]:
    """Convert Goal model to summary dict"""
    progress = calculate_goal_progress(goal)
    target_reps = goal.target_reps if goal.target_reps else 1

    return {
        "id": goal.id,
        "exercise_name": goal.exercise.name if goal.exercise else "Unknown",
        "target_weight": goal.target_weight,
        "target_reps": target_reps,
        "target_e1rm": progress["target_e1rm"],
        "weight_unit": goal.weight_unit,
        "deadline": goal.deadline.isoformat(),
        "progress_percent": progress["progress_percent"],
        "status": goal.status
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
