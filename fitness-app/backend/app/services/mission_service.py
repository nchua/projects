"""
Mission Service - Goals, weekly missions, and AI-powered coaching
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import OperationalError, ProgrammingError
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, Set
import uuid
import logging

logger = logging.getLogger(__name__)

from app.models.mission import (
    Goal, GoalProgressSnapshot, WeeklyMission, MissionWorkout, ExercisePrescription, MissionGoal,
    GoalStatus, MissionStatus, MissionWorkoutStatus, TrainingSplit
)
from app.models.workout import WorkoutSession, WorkoutExercise
from app.models.exercise import Exercise
from app.models.pr import PR
from app.core.utils import to_iso8601_utc
from app.services.exercise_equivalence import get_equivalent_exercise_ids
from app.services.accessory_templates import (
    get_accessory_group,
    get_accessories_for_group,
    ACCESSORY_TEMPLATES,
    VOLUME_ACCESSORY_TEMPLATES,
)


# Maximum number of active goals per user
MAX_ACTIVE_GOALS = 5

# Cache for exercise name -> ID lookups (populated lazily)
_exercise_id_cache: Dict[str, Optional[str]] = {}

# Exercise muscle group mappings for training split determination
EXERCISE_MUSCLE_MAP = {
    # Push exercises (chest, shoulders, triceps)
    "bench": "push", "bench press": "push", "incline bench": "push", "decline bench": "push",
    "overhead press": "push", "ohp": "push", "shoulder press": "push", "military press": "push",
    "dumbbell press": "push", "dips": "push", "tricep": "push", "chest fly": "push",
    # Pull exercises (back, biceps)
    "deadlift": "pull", "row": "pull", "pull-up": "pull", "pullup": "pull", "chin-up": "pull",
    "chinup": "pull", "lat pulldown": "pull", "pulldown": "pull", "curl": "pull", "bicep": "pull",
    "barbell row": "pull", "bent over row": "pull", "face pull": "pull",
    # Leg exercises
    "squat": "legs", "leg press": "legs", "lunge": "legs", "leg extension": "legs",
    "leg curl": "legs", "hamstring": "legs", "calf": "legs", "romanian deadlift": "legs",
    "rdl": "legs", "hip thrust": "legs", "glute": "legs", "front squat": "legs",
}


def get_muscle_group(exercise_name: str) -> str:
    """Determine muscle group from exercise name.

    Keywords are checked longest-first to ensure specific matches like
    "leg curl" take precedence over generic matches like "curl".
    """
    name_lower = exercise_name.lower()
    # Sort keywords by length (longest first) so specific matches take precedence
    # e.g., "leg curl" matches before "curl"
    for keyword in sorted(EXERCISE_MUSCLE_MAP.keys(), key=len, reverse=True):
        if keyword in name_lower:
            return EXERCISE_MUSCLE_MAP[keyword]
    # Default to full body if unknown
    return "full_body"


def get_today_utc() -> date:
    """Get today's date in UTC"""
    return datetime.now(timezone.utc).date()


def get_week_boundaries(target_date: date) -> tuple[date, date]:
    """Get Monday and Sunday of the week containing the given date"""
    # weekday() returns 0 for Monday, 6 for Sunday
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


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


# ============ Prescription Weight Helpers ============

def _get_target_e1rm(goal: Goal) -> float:
    """Calculate target e1RM based on goal target weight/reps."""
    target_reps = goal.target_reps if goal.target_reps else 1
    return calculate_e1rm(goal.target_weight, target_reps)


def _get_projected_e1rm(goal: Goal) -> float:
    """
    Calculate this week's projected e1RM by linearly progressing toward target.

    base_e1rm: current > starting > 85% of target
    projected_e1rm: base + (target - base) / weeks_remaining
    """
    target_e1rm = _get_target_e1rm(goal)
    if target_e1rm <= 0:
        return 0

    base_e1rm = goal.current_e1rm or goal.starting_e1rm or (0.85 * target_e1rm)
    weeks_remaining = max(1, weeks_until(goal.deadline))

    projected_e1rm = base_e1rm + (target_e1rm - base_e1rm) / weeks_remaining
    return min(target_e1rm, projected_e1rm)


def _rep_intensity(reps: int) -> float:
    """Map reps to intensity percentage of projected e1RM."""
    rep_map = {
        5: 0.85,
        6: 0.82,
        8: 0.75,
        10: 0.70,
    }
    if reps in rep_map:
        return rep_map[reps]
    if reps <= 0:
        return 0
    # Fallback: inverse of Epley
    return 1 / (1 + reps / 30)


def _round_prescribed_weight(weight: float, weight_unit: str) -> float:
    """Round to nearest 5 lb or 2.5 kg."""
    if weight <= 0:
        return 0
    increment = 2.5 if weight_unit == "kg" else 5
    return round(weight / increment) * increment


def _prescribed_weight(goal: Goal, reps: int) -> Optional[float]:
    """Compute prescribed weight for a given rep scheme.

    Falls back to 70% of target_weight if no e1RM data is available.
    This ensures all prescriptions have weights even for brand new goals.
    """
    projected_e1rm = _get_projected_e1rm(goal)

    # Fallback: use 70% of target weight if no e1RM data
    if projected_e1rm <= 0:
        if goal.target_weight and goal.target_weight > 0:
            projected_e1rm = goal.target_weight * 0.70
        else:
            return None

    intensity = _rep_intensity(reps)
    if intensity <= 0:
        return None
    weight = projected_e1rm * intensity
    rounded = _round_prescribed_weight(weight, goal.weight_unit)
    return rounded if rounded > 0 else None


def _intensity_note(reps: int) -> str:
    """Return a human-friendly intensity note for a rep scheme."""
    intensity = _rep_intensity(reps)
    if intensity <= 0:
        return "Focus on form and progressive overload"
    percent = int(round(intensity * 100))
    return f"~{percent}% projected 1RM"


def _get_exercise_id_by_name(db: Session, exercise_name: str) -> Optional[str]:
    """Look up exercise ID by name, using cache to avoid repeated queries."""
    global _exercise_id_cache

    if exercise_name in _exercise_id_cache:
        return _exercise_id_cache[exercise_name]

    exercise = db.query(Exercise).filter(
        Exercise.name == exercise_name
    ).first()

    exercise_id = exercise.id if exercise else None
    _exercise_id_cache[exercise_name] = exercise_id
    return exercise_id


def _generate_accessory_prescriptions(
    db: Session,
    primary_weight: float,
    weight_unit: str,
    muscle_group: str,
    is_volume_day: bool = False,
    limit: int = 4
) -> List[Dict[str, Any]]:
    """
    Generate accessory exercise prescriptions based on the primary lift.

    Args:
        db: Database session for exercise lookups
        primary_weight: Weight of the primary lift (for calculating accessory weights)
        weight_unit: 'lb' or 'kg'
        muscle_group: 'push', 'pull', or 'legs'
        is_volume_day: Use volume templates (higher reps, lower weight)
        limit: Maximum number of accessories

    Returns:
        List of prescription dicts ready for workout template
    """
    accessories = get_accessories_for_group(muscle_group, is_volume_day, limit)
    prescriptions = []

    for acc in accessories:
        exercise_id = _get_exercise_id_by_name(db, acc["exercise_name"])
        if not exercise_id:
            # Skip if exercise not found in database
            logger.debug(f"Accessory exercise not found: {acc['exercise_name']}")
            continue

        # Calculate weight as percentage of primary lift
        acc_weight = primary_weight * acc["weight_pct"]
        rounded_weight = _round_prescribed_weight(acc_weight, weight_unit)

        prescriptions.append({
            "exercise_id": exercise_id,
            "sets": acc["sets"],
            "reps": acc["reps"],
            "weight": rounded_weight if rounded_weight > 0 else None,
            "weight_unit": weight_unit,
            "notes": f"Accessory work"
        })

    return prescriptions


def _generate_weekly_target(goals: List[Goal]) -> str:
    """Build the weekly target message based on active goals."""
    goal_names = [g.exercise.name for g in goals if g.exercise]
    if len(goal_names) == 1:
        return f"Focus on {goal_names[0]}"
    if len(goal_names) <= 3:
        return f"Build strength in {', '.join(goal_names)}"
    return f"Progress all {len(goal_names)} goals this week"


def _get_mission_goal_ids(mission: WeeklyMission) -> Set[str]:
    """Get goal IDs tied to the mission (junction table or legacy)."""
    mission_goal_ids: Set[str] = set()
    try:
        if mission.mission_goals:
            for mg in mission.mission_goals:
                if mg.goal_id:
                    mission_goal_ids.add(mg.goal_id)
                elif mg.goal and mg.goal.id:
                    mission_goal_ids.add(mg.goal.id)
    except (OperationalError, ProgrammingError, Exception) as e:
        logger.warning(f"Failed to access mission_goals: {e}. Using legacy goal.")

    if not mission_goal_ids and mission.goal and mission.goal.id:
        mission_goal_ids.add(mission.goal.id)

    return mission_goal_ids


def needs_backfill(mission: WeeklyMission, active_goals: List[Goal]) -> bool:
    """Determine if the current mission should be backfilled."""
    workouts_completed = sum(
        1 for w in mission.workouts if w.status == MissionWorkoutStatus.COMPLETED.value
    )
    if workouts_completed > 0:
        return False

    # Missing weights
    for workout in mission.workouts:
        for prescription in workout.prescriptions or []:
            if prescription.weight is None:
                return True

    # Accessory day missing prescriptions (single-goal)
    if len(active_goals) == 1:
        for workout in mission.workouts:
            focus = (workout.focus or "").lower()
            if "accessory" in focus and len(workout.prescriptions or []) == 0:
                return True

    # Mission goals not covering all active goals
    active_goal_ids = {g.id for g in active_goals}
    mission_goal_ids = _get_mission_goal_ids(mission)
    if active_goal_ids != mission_goal_ids:
        return True

    return False


def backfill_current_mission(db: Session, mission: WeeklyMission, active_goals: List[Goal]) -> WeeklyMission:
    """Backfill an existing mission with updated prescriptions and weights."""
    if not active_goals:
        return mission

    # Ensure mission goals cover all active goals
    mission_goal_ids = _get_mission_goal_ids(mission)
    for goal in active_goals:
        if goal.id not in mission_goal_ids:
            mission_goal = MissionGoal(
                id=str(uuid.uuid4()),
                mission_id=mission.id,
                goal_id=goal.id,
                workouts_completed=0,
                is_satisfied=False
            )
            db.add(mission_goal)
            if hasattr(mission, "mission_goals") and mission.mission_goals is not None:
                mission.mission_goals.append(mission_goal)
            mission_goal_ids.add(goal.id)

    # Update primary goal for legacy fields
    mission.goal_id = active_goals[0].id

    # Recompute training split and messaging
    training_split = determine_training_split(active_goals)
    mission.training_split = training_split.value
    mission.weekly_target = _generate_weekly_target(active_goals)
    mission.coaching_message = _generate_coaching_message(active_goals, training_split)

    # Generate updated workout templates
    workout_templates = _generate_workout_templates(active_goals, training_split, db)
    template_by_day = {t["day"]: t for t in workout_templates}

    # Update workouts by day
    workouts_by_day = {w.day_number: w for w in mission.workouts}
    for day, template in template_by_day.items():
        workout = workouts_by_day.get(day)
        if not workout:
            workout = MissionWorkout(
                id=str(uuid.uuid4()),
                mission_id=mission.id,
                day_number=day,
                focus=template["focus"],
                primary_lift=template.get("primary_lift"),
                status=MissionWorkoutStatus.PENDING.value
            )
            db.add(workout)
            mission.workouts.append(workout)
        else:
            workout.focus = template["focus"]
            workout.primary_lift = template.get("primary_lift")

        # Remove existing prescriptions
        for prescription in list(workout.prescriptions or []):
            db.delete(prescription)
        workout.prescriptions = []

        # Add new prescriptions
        for idx, prescription_data in enumerate(template.get("prescriptions", [])):
            prescription = ExercisePrescription(
                id=str(uuid.uuid4()),
                mission_workout_id=workout.id,
                exercise_id=prescription_data["exercise_id"],
                order_index=idx,
                sets=prescription_data["sets"],
                reps=prescription_data["reps"],
                weight=prescription_data.get("weight"),
                weight_unit=prescription_data.get("weight_unit", "lb"),
                notes=prescription_data.get("notes", "Focus on form and progressive overload")
            )
            db.add(prescription)
            workout.prescriptions.append(prescription)

    db.flush()
    return mission


# ============ Goal Functions ============

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
            goal.abandoned_at = datetime.utcnow()
        elif status == GoalStatus.COMPLETED.value:
            goal.achieved_at = datetime.utcnow()

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
        # Update current e1RM if this is higher
        if goal.current_e1rm is None or new_e1rm > goal.current_e1rm:
            goal.current_e1rm = new_e1rm

            # Record progress snapshot
            snapshot = GoalProgressSnapshot(
                id=str(uuid.uuid4()),
                goal_id=goal.id,
                recorded_at=datetime.utcnow(),
                e1rm=new_e1rm,
                weight=weight,
                reps=reps,
                workout_id=workout_id
            )
            db.add(snapshot)

        # Calculate target e1RM (accounts for target_reps)
        target_e1rm = calculate_e1rm(goal.target_weight, goal.target_reps)

        # Check if goal is achieved (compare e1RMs)
        if new_e1rm >= target_e1rm and goal.status == GoalStatus.ACTIVE.value:
            goal.status = GoalStatus.COMPLETED.value
            goal.achieved_at = datetime.utcnow()
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


# ============ Mission Functions ============

def determine_training_split(goals: List[Goal]) -> TrainingSplit:
    """
    Determine the optimal training split based on goals.

    Args:
        goals: List of active goals

    Returns:
        TrainingSplit enum value
    """
    if len(goals) == 1:
        return TrainingSplit.SINGLE_FOCUS

    # Determine muscle groups for each goal
    muscle_groups = set()
    for goal in goals:
        if goal.exercise:
            group = get_muscle_group(goal.exercise.name)
            muscle_groups.add(group)

    # If all goals hit same muscle group, use a rotating focus split
    if len(muscle_groups) == 1:
        return TrainingSplit.FULL_BODY

    # Check if goals are diverse
    has_push = "push" in muscle_groups
    has_pull = "pull" in muscle_groups
    has_legs = "legs" in muscle_groups

    # Classic Big Three (squat, bench, deadlift) -> PPL
    if has_push and has_pull and has_legs:
        return TrainingSplit.PPL

    # Upper body only or lower body only
    if (has_push or has_pull) and not has_legs:
        return TrainingSplit.UPPER_LOWER
    if has_legs and not (has_push or has_pull):
        return TrainingSplit.UPPER_LOWER

    # 4-5 goals with diverse muscle groups
    if len(goals) >= 4:
        return TrainingSplit.PPL

    # Default to PPL for 2-3 diverse goals
    return TrainingSplit.PPL


def get_or_create_current_mission(db: Session, user_id: str) -> Dict[str, Any]:
    """
    Get the current week's mission, or generate one if needed.

    Returns a dict with:
    - has_active_goals: bool (plural)
    - goals: List[GoalSummary] (all active goals)
    - mission: MissionSummary or None
    - needs_goal_setup: bool
    - can_add_more_goals: bool (True if < 5 goals)
    """
    # Check for active goals
    active_goals = get_user_goals(db, user_id, include_inactive=False)

    if not active_goals:
        return {
            "has_active_goal": False,  # Keep for backwards compatibility
            "has_active_goals": False,
            "goal": None,  # Keep for backwards compatibility
            "goals": [],
            "mission": None,
            "needs_goal_setup": True,
            "can_add_more_goals": True
        }

    # Get week boundaries
    today = get_today_utc()
    week_start, week_end = get_week_boundaries(today)

    # Check for existing mission this week (using junction table for multi-goal)
    try:
        mission = db.query(WeeklyMission).options(
            joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions),
            joinedload(WeeklyMission.mission_goals).joinedload(MissionGoal.goal).joinedload(Goal.exercise),
            joinedload(WeeklyMission.goal).joinedload(Goal.exercise)  # Legacy support
        ).filter(
            WeeklyMission.user_id == user_id,
            WeeklyMission.week_start == week_start
        ).first()
    except (OperationalError, ProgrammingError) as e:
        # Handle case where mission_goals table doesn't exist yet (migration not applied)
        logger.warning(f"Failed to query missions with mission_goals join: {e}. Trying legacy query.")
        # Fallback to legacy query without mission_goals
        mission = db.query(WeeklyMission).options(
            joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions),
            joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
        ).filter(
            WeeklyMission.user_id == user_id,
            WeeklyMission.week_start == week_start
        ).first()

    # Build goals summary (use all active goals)
    goals_summary = [goal_to_summary(g) for g in active_goals]
    primary_goal_summary = goals_summary[0] if goals_summary else None

    # If no mission exists and it's Sunday or Monday, create one
    if not mission:
        # Only auto-generate on Sunday (6) or Monday (0)
        if today.weekday() in [0, 6]:
            mission = generate_multi_goal_mission(db, user_id, active_goals, week_start, week_end)
        else:
            # Mid-week with no mission - they can still create goals
            return {
                "has_active_goal": True,
                "has_active_goals": len(active_goals) > 0,
                "goal": primary_goal_summary,
                "goals": goals_summary,
                "mission": None,
                "needs_goal_setup": False,
                "can_add_more_goals": len(active_goals) < MAX_ACTIVE_GOALS
            }

    # Backfill existing mission if needed (only when 0 workouts completed)
    if mission and needs_backfill(mission, active_goals):
        mission = backfill_current_mission(db, mission, active_goals)

    return {
        "has_active_goal": True,
        "has_active_goals": len(active_goals) > 0,
        "goal": primary_goal_summary,
        "goals": goals_summary,
        "mission": mission_to_summary(mission) if mission else None,
        "needs_goal_setup": False,
        "can_add_more_goals": len(active_goals) < MAX_ACTIVE_GOALS
    }


def generate_weekly_mission(
    db: Session,
    user_id: str,
    goal: Goal,
    week_start: date,
    week_end: date
) -> WeeklyMission:
    """
    Generate a weekly mission based on a single goal.
    Delegates to generate_multi_goal_mission for consistency.
    """
    return generate_multi_goal_mission(db, user_id, [goal], week_start, week_end)


def generate_multi_goal_mission(
    db: Session,
    user_id: str,
    goals: List[Goal],
    week_start: date,
    week_end: date
) -> WeeklyMission:
    """
    Generate a weekly mission based on multiple goals.

    Creates an intelligent training split (PPL, Upper/Lower, etc.) to
    work towards all goals simultaneously.

    Args:
        db: Database session
        user_id: User ID
        goals: List of active goals (1-5)
        week_start: Monday of the week
        week_end: Sunday of the week

    Returns:
        WeeklyMission with workouts targeting all goals
    """
    if not goals:
        raise ValueError("At least one goal is required")

    # Determine training split
    training_split = determine_training_split(goals)

    # Build goal names for weekly target message
    target_msg = _generate_weekly_target(goals)

    # Calculate XP reward (50 base + 50 per goal)
    xp_reward = 50 + (50 * len(goals))

    # Create mission (legacy goal_id set to first goal for backwards compat)
    mission = WeeklyMission(
        id=str(uuid.uuid4()),
        user_id=user_id,
        goal_id=goals[0].id,  # Legacy: primary goal
        training_split=training_split.value,
        week_start=week_start,
        week_end=week_end,
        status=MissionStatus.OFFERED.value,
        xp_reward=xp_reward,
        weekly_target=target_msg,
        coaching_message=_generate_coaching_message(goals, training_split)
    )

    db.add(mission)
    db.flush()

    # Create mission_goal entries for each goal
    for goal in goals:
        mission_goal = MissionGoal(
            id=str(uuid.uuid4()),
            mission_id=mission.id,
            goal_id=goal.id,
            workouts_completed=0,
            is_satisfied=False
        )
        db.add(mission_goal)

    # Generate workouts based on training split
    workout_templates = _generate_workout_templates(goals, training_split, db)

    for template in workout_templates:
        workout = MissionWorkout(
            id=str(uuid.uuid4()),
            mission_id=mission.id,
            day_number=template["day"],
            focus=template["focus"],
            primary_lift=template.get("primary_lift"),
            status=MissionWorkoutStatus.PENDING.value
        )
        db.add(workout)
        db.flush()

        # Add exercise prescriptions
        for idx, prescription_data in enumerate(template.get("prescriptions", [])):
            prescription = ExercisePrescription(
                id=str(uuid.uuid4()),
                mission_workout_id=workout.id,
                exercise_id=prescription_data["exercise_id"],
                order_index=idx,
                sets=prescription_data["sets"],
                reps=prescription_data["reps"],
                weight=prescription_data.get("weight"),
                weight_unit=prescription_data.get("weight_unit", "lb"),
                notes=prescription_data.get("notes", "Focus on form and progressive overload")
            )
            db.add(prescription)

    db.flush()

    # Reload with relationships
    mission = db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions).joinedload(ExercisePrescription.exercise),
        joinedload(WeeklyMission.mission_goals).joinedload(MissionGoal.goal).joinedload(Goal.exercise),
        joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
    ).filter(WeeklyMission.id == mission.id).first()

    return mission


def _generate_coaching_message(goals: List[Goal], split: TrainingSplit) -> str:
    """Generate a coaching message based on goals and split"""
    if len(goals) == 1:
        return "Complete these workouts this week to progress toward your goal!"

    split_name = {
        TrainingSplit.SINGLE_FOCUS: "focused program",
        TrainingSplit.PPL: "Push/Pull/Legs split",
        TrainingSplit.UPPER_LOWER: "Upper/Lower split",
        TrainingSplit.FULL_BODY: "Full Body program",
    }.get(split, "training program")

    return f"This week's {split_name} targets all {len(goals)} of your goals. Complete each workout to make progress!"


def _generate_workout_templates(
    goals: List[Goal],
    split: TrainingSplit,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Generate workout templates based on goals and training split.

    Args:
        goals: List of active goals
        split: Training split type
        db: Optional database session for accessory exercise lookups

    Returns list of workout dicts with day, focus, primary_lift, and prescriptions.
    """
    if _all_goals_same_group(goals):
        return _generate_same_group_workouts(goals, db)

    if split == TrainingSplit.SINGLE_FOCUS or len(goals) == 1:
        return _generate_single_focus_workouts(goals[0], db)

    if split == TrainingSplit.PPL:
        return _generate_ppl_workouts(goals, db)

    if split == TrainingSplit.UPPER_LOWER:
        return _generate_upper_lower_workouts(goals, db)

    # Default: full body
    return _generate_full_body_workouts(goals, db)


def _all_goals_same_group(goals: List[Goal]) -> bool:
    """Check if all goals map to the same muscle group."""
    if len(goals) <= 1:
        return False

    muscle_groups = set()
    for goal in goals:
        if goal.exercise:
            muscle_groups.add(get_muscle_group(goal.exercise.name))

    return len(muscle_groups) == 1


def _generate_same_group_workouts(
    goals: List[Goal],
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """Rotate focus across goals that share the same muscle group."""
    goals_with_exercise = [g for g in goals if g.exercise_id and g.exercise]
    if len(goals_with_exercise) <= 1:
        return _generate_single_focus_workouts(goals_with_exercise[0], db) if goals_with_exercise else []

    goals_sorted = sorted(goals_with_exercise, key=lambda g: g.exercise.name)
    primary_a = goals_sorted[0]
    primary_b = goals_sorted[1]
    others = goals_sorted[2:]

    group_label = get_muscle_group(primary_a.exercise.name)
    label_map = {
        "push": "Push",
        "pull": "Pull",
        "legs": "Legs",
        "full_body": "Full Body"
    }
    volume_label = label_map.get(group_label, "Volume")

    def light_prescriptions(exclude_goal_id: str) -> List[Dict[str, Any]]:
        prescriptions = []
        for goal in goals_sorted:
            if goal.id == exclude_goal_id:
                continue
            prescriptions.append({
                "exercise_id": goal.exercise_id,
                "sets": 2,
                "reps": 8,
                "weight": _prescribed_weight(goal, 8),
                "weight_unit": goal.weight_unit,
                "notes": f"Supporting volume ({_intensity_note(8)})"
            })
        return prescriptions

    return [
        {
            "day": 1,
            "focus": f"Heavy {primary_a.exercise.name}",
            "primary_lift": primary_a.exercise.name,
            "prescriptions": [
                {
                    "exercise_id": primary_a.exercise_id,
                    "sets": 4,
                    "reps": 5,
                    "weight": _prescribed_weight(primary_a, 5),
                    "weight_unit": primary_a.weight_unit,
                    "notes": f"Heavy working sets - {_intensity_note(5)}"
                },
                *light_prescriptions(primary_a.id)
            ]
        },
        {
            "day": 2,
            "focus": f"Heavy {primary_b.exercise.name}",
            "primary_lift": primary_b.exercise.name,
            "prescriptions": [
                {
                    "exercise_id": primary_b.exercise_id,
                    "sets": 4,
                    "reps": 5,
                    "weight": _prescribed_weight(primary_b, 5),
                    "weight_unit": primary_b.weight_unit,
                    "notes": f"Heavy working sets - {_intensity_note(5)}"
                },
                *light_prescriptions(primary_b.id)
            ]
        },
        {
            "day": 3,
            "focus": f"Volume {volume_label}",
            "primary_lift": primary_a.exercise.name,
            "prescriptions": [
                {
                    "exercise_id": goal.exercise_id,
                    "sets": 3,
                    "reps": 10,
                    "weight": _prescribed_weight(goal, 10),
                    "weight_unit": goal.weight_unit,
                    "notes": f"Volume work - {_intensity_note(10)}"
                }
                for goal in goals_sorted
            ]
        }
    ]


def _generate_single_focus_workouts(
    goal: Goal,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """Generate 3-day Heavy/Accessory/Volume split for single goal with accessories."""
    exercise_name = goal.exercise.name if goal.exercise else "Main Lift"
    exercise_id = goal.exercise_id
    heavy_reps = 5
    accessory_reps = 8
    volume_reps = 10

    # Determine muscle group for accessory selection
    muscle_group = get_muscle_group(exercise_name)

    # Calculate primary lift weights for accessory weight calculation
    heavy_weight = _prescribed_weight(goal, heavy_reps)
    accessory_weight = _prescribed_weight(goal, accessory_reps)
    volume_weight = _prescribed_weight(goal, volume_reps)

    # Get accessory exercises if db is available
    heavy_accessories = []
    day2_accessories = []
    volume_accessories = []

    if db and heavy_weight:
        heavy_accessories = _generate_accessory_prescriptions(
            db, heavy_weight, goal.weight_unit, muscle_group, is_volume_day=False, limit=3
        )
    if db and accessory_weight:
        day2_accessories = _generate_accessory_prescriptions(
            db, accessory_weight, goal.weight_unit, muscle_group, is_volume_day=False, limit=4
        )
    if db and volume_weight:
        volume_accessories = _generate_accessory_prescriptions(
            db, volume_weight, goal.weight_unit, muscle_group, is_volume_day=True, limit=3
        )

    workouts = [
        {
            "day": 1,
            "focus": f"Heavy {exercise_name}",
            "primary_lift": exercise_name,
            "prescriptions": [
                {
                    "exercise_id": exercise_id,
                    "sets": 4,
                    "reps": heavy_reps,
                    "weight": heavy_weight,
                    "weight_unit": goal.weight_unit,
                    "notes": f"Heavy working sets - {_intensity_note(heavy_reps)}"
                },
                *heavy_accessories
            ] if exercise_id else []
        },
        {
            "day": 2,
            "focus": "Accessory Work",
            "primary_lift": exercise_name,
            "prescriptions": [
                {
                    "exercise_id": exercise_id,
                    "sets": 3,
                    "reps": accessory_reps,
                    "weight": accessory_weight,
                    "weight_unit": goal.weight_unit,
                    "notes": f"Moderate weight - {_intensity_note(accessory_reps)}"
                },
                *day2_accessories
            ] if exercise_id else []
        },
        {
            "day": 3,
            "focus": f"Volume {exercise_name}",
            "primary_lift": exercise_name,
            "prescriptions": [
                {
                    "exercise_id": exercise_id,
                    "sets": 3,
                    "reps": volume_reps,
                    "weight": volume_weight,
                    "weight_unit": goal.weight_unit,
                    "notes": f"Volume work - {_intensity_note(volume_reps)}"
                },
                *volume_accessories
            ] if exercise_id else []
        }
    ]

    return workouts


def _generate_ppl_workouts(
    goals: List[Goal],
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """Generate Push/Pull/Legs split for multiple goals with accessories."""
    # Categorize goals by muscle group
    push_goals = []
    pull_goals = []
    leg_goals = []

    for goal in goals:
        if goal.exercise:
            group = get_muscle_group(goal.exercise.name)
            if group == "push":
                push_goals.append(goal)
            elif group == "pull":
                pull_goals.append(goal)
            elif group == "legs":
                leg_goals.append(goal)
            else:
                # Unknown - add to whichever is emptiest
                min_list = min([push_goals, pull_goals, leg_goals], key=len)
                min_list.append(goal)

    workouts = []

    # Push Day
    push_prescriptions = []
    push_primary_weight = None
    for goal in push_goals:
        if goal.exercise_id:
            reps = 6
            weight = _prescribed_weight(goal, reps)
            if push_primary_weight is None:
                push_primary_weight = weight
            push_prescriptions.append({
                "exercise_id": goal.exercise_id,
                "sets": 4,
                "reps": reps,
                "weight": weight,
                "weight_unit": goal.weight_unit,
                "notes": f"Focus on {goal.exercise.name} ({_intensity_note(reps)})"
            })

    # Add push accessories if we have a primary weight and db
    if db and push_primary_weight and push_goals:
        push_accessories = _generate_accessory_prescriptions(
            db, push_primary_weight, push_goals[0].weight_unit, "push", is_volume_day=False, limit=3
        )
        push_prescriptions.extend(push_accessories)

    workouts.append({
        "day": 1,
        "focus": "Push - " + (push_goals[0].exercise.name if push_goals and push_goals[0].exercise else "Chest/Shoulders"),
        "primary_lift": push_goals[0].exercise.name if push_goals and push_goals[0].exercise else None,
        "prescriptions": push_prescriptions
    })

    # Pull Day
    pull_prescriptions = []
    pull_primary_weight = None
    for goal in pull_goals:
        if goal.exercise_id:
            reps = 6
            weight = _prescribed_weight(goal, reps)
            if pull_primary_weight is None:
                pull_primary_weight = weight
            pull_prescriptions.append({
                "exercise_id": goal.exercise_id,
                "sets": 4,
                "reps": reps,
                "weight": weight,
                "weight_unit": goal.weight_unit,
                "notes": f"Focus on {goal.exercise.name} ({_intensity_note(reps)})"
            })

    # Add pull accessories
    if db and pull_primary_weight and pull_goals:
        pull_accessories = _generate_accessory_prescriptions(
            db, pull_primary_weight, pull_goals[0].weight_unit, "pull", is_volume_day=False, limit=3
        )
        pull_prescriptions.extend(pull_accessories)

    workouts.append({
        "day": 2,
        "focus": "Pull - " + (pull_goals[0].exercise.name if pull_goals and pull_goals[0].exercise else "Back/Biceps"),
        "primary_lift": pull_goals[0].exercise.name if pull_goals and pull_goals[0].exercise else None,
        "prescriptions": pull_prescriptions
    })

    # Legs Day
    leg_prescriptions = []
    leg_primary_weight = None
    for goal in leg_goals:
        if goal.exercise_id:
            reps = 6
            weight = _prescribed_weight(goal, reps)
            if leg_primary_weight is None:
                leg_primary_weight = weight
            leg_prescriptions.append({
                "exercise_id": goal.exercise_id,
                "sets": 4,
                "reps": reps,
                "weight": weight,
                "weight_unit": goal.weight_unit,
                "notes": f"Focus on {goal.exercise.name} ({_intensity_note(reps)})"
            })

    # Add legs accessories
    if db and leg_primary_weight and leg_goals:
        leg_accessories = _generate_accessory_prescriptions(
            db, leg_primary_weight, leg_goals[0].weight_unit, "legs", is_volume_day=False, limit=3
        )
        leg_prescriptions.extend(leg_accessories)

    workouts.append({
        "day": 3,
        "focus": "Legs - " + (leg_goals[0].exercise.name if leg_goals and leg_goals[0].exercise else "Quads/Hamstrings"),
        "primary_lift": leg_goals[0].exercise.name if leg_goals and leg_goals[0].exercise else None,
        "prescriptions": leg_prescriptions
    })

    # Filter out days with no prescriptions (e.g., user has goals in only 2 categories)
    workouts = [w for w in workouts if w["prescriptions"]]

    # Renumber days after filtering
    for i, workout in enumerate(workouts, start=1):
        workout["day"] = i

    return workouts


def _generate_upper_lower_workouts(
    goals: List[Goal],
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """Generate Upper/Lower split for goals with accessories."""
    upper_goals = []
    lower_goals = []

    for goal in goals:
        if goal.exercise:
            group = get_muscle_group(goal.exercise.name)
            if group in ["push", "pull"]:
                upper_goals.append(goal)
            else:
                lower_goals.append(goal)

    workouts = []

    # Upper Day 1 (heavy)
    upper_prescriptions = []
    upper_primary_weight = None
    for goal in upper_goals:
        if goal.exercise_id:
            reps = 5
            weight = _prescribed_weight(goal, reps)
            if upper_primary_weight is None:
                upper_primary_weight = weight
            upper_prescriptions.append({
                "exercise_id": goal.exercise_id,
                "sets": 4,
                "reps": reps,
                "weight": weight,
                "weight_unit": goal.weight_unit,
                "notes": f"Heavy {goal.exercise.name} ({_intensity_note(reps)})"
            })

    # Add upper accessories (mix of push and pull)
    if db and upper_primary_weight and upper_goals:
        push_acc = _generate_accessory_prescriptions(
            db, upper_primary_weight, upper_goals[0].weight_unit, "push", is_volume_day=False, limit=2
        )
        pull_acc = _generate_accessory_prescriptions(
            db, upper_primary_weight, upper_goals[0].weight_unit, "pull", is_volume_day=False, limit=2
        )
        upper_prescriptions.extend(push_acc[:1])  # 1 push accessory
        upper_prescriptions.extend(pull_acc[:1])  # 1 pull accessory

    workouts.append({
        "day": 1,
        "focus": "Upper Body (Heavy)",
        "primary_lift": upper_goals[0].exercise.name if upper_goals and upper_goals[0].exercise else None,
        "prescriptions": upper_prescriptions
    })

    # Lower Day
    lower_prescriptions = []
    lower_primary_weight = None
    for goal in lower_goals:
        if goal.exercise_id:
            reps = 5
            weight = _prescribed_weight(goal, reps)
            if lower_primary_weight is None:
                lower_primary_weight = weight
            lower_prescriptions.append({
                "exercise_id": goal.exercise_id,
                "sets": 4,
                "reps": reps,
                "weight": weight,
                "weight_unit": goal.weight_unit,
                "notes": f"Heavy {goal.exercise.name} ({_intensity_note(reps)})"
            })

    # Add legs accessories
    if db and lower_primary_weight and lower_goals:
        leg_accessories = _generate_accessory_prescriptions(
            db, lower_primary_weight, lower_goals[0].weight_unit, "legs", is_volume_day=False, limit=3
        )
        lower_prescriptions.extend(leg_accessories)

    workouts.append({
        "day": 2,
        "focus": "Lower Body",
        "primary_lift": lower_goals[0].exercise.name if lower_goals and lower_goals[0].exercise else None,
        "prescriptions": lower_prescriptions
    })

    # Upper Day 2 (volume)
    upper_volume_prescriptions = []
    upper_volume_weight = None
    for goal in upper_goals:
        if goal.exercise_id:
            reps = 10
            weight = _prescribed_weight(goal, reps)
            if upper_volume_weight is None:
                upper_volume_weight = weight
            upper_volume_prescriptions.append({
                "exercise_id": goal.exercise_id,
                "sets": 3,
                "reps": reps,
                "weight": weight,
                "weight_unit": goal.weight_unit,
                "notes": f"Volume {goal.exercise.name} ({_intensity_note(reps)})"
            })

    # Add volume accessories
    if db and upper_volume_weight and upper_goals:
        push_acc = _generate_accessory_prescriptions(
            db, upper_volume_weight, upper_goals[0].weight_unit, "push", is_volume_day=True, limit=2
        )
        pull_acc = _generate_accessory_prescriptions(
            db, upper_volume_weight, upper_goals[0].weight_unit, "pull", is_volume_day=True, limit=2
        )
        upper_volume_prescriptions.extend(push_acc[:1])
        upper_volume_prescriptions.extend(pull_acc[:1])

    workouts.append({
        "day": 3,
        "focus": "Upper Body (Volume)",
        "primary_lift": upper_goals[0].exercise.name if upper_goals and upper_goals[0].exercise else None,
        "prescriptions": upper_volume_prescriptions
    })

    return workouts


def _generate_full_body_workouts(
    goals: List[Goal],
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """Generate full body workouts hitting all goals each session.

    Full body workouts focus on compound movements, so accessories are minimal
    to keep workout duration reasonable.
    """
    workouts = []

    # 3 full body days with varying rep schemes
    rep_schemes = [
        (5, "Heavy", False),
        (8, "Moderate", False),
        (10, "Volume", True)
    ]

    for day, (reps, intensity, is_volume) in enumerate(rep_schemes, 1):
        prescriptions = []
        primary_weight = None
        weight_unit = "lb"

        for goal in goals:
            if goal.exercise_id:
                weight = _prescribed_weight(goal, reps)
                if primary_weight is None:
                    primary_weight = weight
                    weight_unit = goal.weight_unit
                prescriptions.append({
                    "exercise_id": goal.exercise_id,
                    "sets": 3,
                    "reps": reps,
                    "weight": weight,
                    "weight_unit": goal.weight_unit,
                    "notes": f"{intensity} {goal.exercise.name} ({_intensity_note(reps)})"
                })

        # Add 1-2 accessories for full body (keep it simple)
        if db and primary_weight:
            # Rotate muscle groups for accessories
            acc_groups = ["push", "pull", "legs"]
            acc_group = acc_groups[day - 1]  # Different group each day
            accessories = _generate_accessory_prescriptions(
                db, primary_weight, weight_unit, acc_group, is_volume_day=is_volume, limit=2
            )
            prescriptions.extend(accessories[:2])

        workouts.append({
            "day": day,
            "focus": f"Full Body ({intensity})",
            "primary_lift": goals[0].exercise.name if goals[0].exercise else None,
            "prescriptions": prescriptions
        })

    return workouts


def get_mission_by_id(db: Session, user_id: str, mission_id: str) -> Optional[WeeklyMission]:
    """Get a specific mission with all relationships loaded"""
    return db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions).joinedload(ExercisePrescription.exercise),
        joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
    ).filter(
        WeeklyMission.id == mission_id,
        WeeklyMission.user_id == user_id
    ).first()


def accept_mission(db: Session, user_id: str, mission_id: str) -> Dict[str, Any]:
    """
    Accept a weekly mission.

    Args:
        db: Database session
        user_id: User ID
        mission_id: Mission to accept

    Returns:
        Dict with success status and mission details

    Raises:
        ValueError: If mission not found or cannot be accepted
    """
    mission = get_mission_by_id(db, user_id, mission_id)

    if not mission:
        raise ValueError("Mission not found")

    if mission.status != MissionStatus.OFFERED.value:
        raise ValueError(f"Mission cannot be accepted (status: {mission.status})")

    # Check if mission has expired
    if mission.week_end < get_today_utc():
        mission.status = MissionStatus.EXPIRED.value
        db.flush()
        raise ValueError("Mission has expired")

    mission.status = MissionStatus.ACCEPTED.value
    mission.accepted_at = datetime.utcnow()

    db.flush()

    return {
        "success": True,
        "mission": mission_to_response(mission),
        "message": "Mission accepted! Complete your workouts this week."
    }


def decline_mission(db: Session, user_id: str, mission_id: str) -> Dict[str, Any]:
    """Decline a weekly mission"""
    mission = get_mission_by_id(db, user_id, mission_id)

    if not mission:
        raise ValueError("Mission not found")

    if mission.status != MissionStatus.OFFERED.value:
        raise ValueError(f"Mission cannot be declined (status: {mission.status})")

    mission.status = MissionStatus.DECLINED.value
    mission.declined_at = datetime.utcnow()

    db.flush()

    return {
        "success": True,
        "message": "Mission declined. Daily quests will continue as normal."
    }


def check_mission_workout_completion(
    db: Session,
    user_id: str,
    workout: WorkoutSession
) -> Dict[str, Any]:
    """
    Check if a logged workout completes any mission workouts.

    Uses exercise equivalence to match similar exercises (e.g., Incline Bench → Bench goal).
    Credits ALL matching goals from one workout (not just one).

    Args:
        db: Database session
        user_id: User ID
        workout: The completed workout session (must have relationships loaded)

    Returns:
        Dict with missions/workouts that were progressed or completed
    """
    result = {
        "mission_workouts_completed": [],
        "missions_completed": [],
        "goals_progressed": [],
        "xp_earned": 0
    }

    # Get active missions with goals loaded
    active_missions = db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions),
        joinedload(WeeklyMission.mission_goals).joinedload(MissionGoal.goal).joinedload(Goal.exercise),
        joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
    ).filter(
        WeeklyMission.user_id == user_id,
        WeeklyMission.status == MissionStatus.ACCEPTED.value
    ).all()

    if not active_missions:
        return result

    # Get exercise IDs from the logged workout
    logged_exercise_ids = set()
    for we in workout.workout_exercises:
        logged_exercise_ids.add(we.exercise_id)

    for mission in active_missions:
        # Get all goals for this mission (from junction table or legacy single goal)
        mission_goals = [mg for mg in mission.mission_goals] if mission.mission_goals else []
        if not mission_goals and mission.goal:
            # Create a pseudo MissionGoal for legacy single-goal missions
            class LegacyMissionGoal:
                def __init__(self, goal):
                    self.goal = goal
                    self.workouts_completed = 0
                    self.is_satisfied = False
            mission_goals = [LegacyMissionGoal(mission.goal)]

        # Track which goals were hit by this workout
        goals_hit_this_workout = []

        # Check each goal for matches (credit ALL matching goals)
        for mission_goal in mission_goals:
            if not mission_goal.goal or not mission_goal.goal.exercise_id:
                continue

            # Get equivalent exercise IDs for this goal
            equivalent_ids = get_equivalent_exercise_ids(mission_goal.goal.exercise_id, db)

            # Check if logged workout includes any equivalent exercise
            if logged_exercise_ids & equivalent_ids:
                goals_hit_this_workout.append(mission_goal)

                # Update per-goal progress (for MissionGoal entries from DB)
                if hasattr(mission_goal, 'id'):  # Real MissionGoal from DB
                    mission_goal.workouts_completed += 1
                    # Goal is satisfied if at least 2 workouts hit it this week
                    if mission_goal.workouts_completed >= 2:
                        mission_goal.is_satisfied = True

                result["goals_progressed"].append({
                    "goal_id": mission_goal.goal.id,
                    "exercise_name": mission_goal.goal.exercise.name if mission_goal.goal.exercise else "Unknown"
                })

        # If any goals were hit, credit a mission workout
        if goals_hit_this_workout:
            for mission_workout in mission.workouts:
                if mission_workout.status != MissionWorkoutStatus.PENDING.value:
                    continue

                # Mark this mission workout as completed
                mission_workout.status = MissionWorkoutStatus.COMPLETED.value
                mission_workout.completed_workout_id = workout.id
                mission_workout.completed_at = datetime.utcnow()

                # Note which goals were progressed
                goal_names = [mg.goal.exercise.name for mg in goals_hit_this_workout
                             if mg.goal and mg.goal.exercise]
                mission_workout.completion_notes = f"Progressed goals: {', '.join(goal_names)}"

                result["mission_workouts_completed"].append({
                    "id": mission_workout.id,
                    "focus": mission_workout.focus,
                    "day_number": mission_workout.day_number,
                    "goals_hit": len(goals_hit_this_workout)
                })

                # Only credit one mission workout per logged workout
                break

        # Check if mission is now complete
        completed_count = sum(1 for mw in mission.workouts if mw.status == MissionWorkoutStatus.COMPLETED.value)
        if completed_count >= len(mission.workouts):
            mission.status = MissionStatus.COMPLETED.value
            mission.completed_at = datetime.utcnow()
            mission.xp_earned = mission.xp_reward

            result["missions_completed"].append({
                "id": mission.id,
                "xp_reward": mission.xp_reward,
                "goals_count": len([mg for mg in mission_goals if mg.goal])
            })
            result["xp_earned"] += mission.xp_reward

    db.flush()
    return result


def get_mission_history(db: Session, user_id: str, limit: int = 10) -> Dict[str, Any]:
    """Get past missions for a user"""
    missions = db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts),
        joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
    ).filter(
        WeeklyMission.user_id == user_id,
        WeeklyMission.status.in_([
            MissionStatus.COMPLETED.value,
            MissionStatus.EXPIRED.value,
            MissionStatus.DECLINED.value
        ])
    ).order_by(WeeklyMission.week_start.desc()).limit(limit).all()

    total_completed = sum(1 for m in missions if m.status == MissionStatus.COMPLETED.value)
    total_xp = sum(m.xp_earned for m in missions)

    return {
        "missions": [mission_to_summary(m) for m in missions],
        "total_completed": total_completed,
        "total_xp_earned": total_xp
    }


def mission_to_response(mission: WeeklyMission) -> Dict[str, Any]:
    """Convert WeeklyMission to full response dict"""
    # Get goals from junction table or legacy single goal
    # Handle case where mission_goals table doesn't exist yet
    try:
        mission_goals = [mg.goal for mg in mission.mission_goals if mg.goal] if mission.mission_goals else []
    except (OperationalError, ProgrammingError, Exception) as e:
        logger.warning(f"Failed to access mission_goals in response: {e}. Using legacy goal.")
        mission_goals = []

    if not mission_goals and mission.goal:
        mission_goals = [mission.goal]

    primary_goal = mission_goals[0] if mission_goals else mission.goal
    workouts_completed = sum(1 for w in mission.workouts if w.status == MissionWorkoutStatus.COMPLETED.value)

    return {
        "id": mission.id,
        "goal_id": mission.goal_id,  # Legacy: primary goal
        "goal_exercise_name": primary_goal.exercise.name if primary_goal and primary_goal.exercise else "Unknown",
        "goal_target_weight": primary_goal.target_weight if primary_goal else 0,
        "goal_weight_unit": primary_goal.weight_unit if primary_goal else "lb",
        "training_split": mission.training_split,
        "goals": [goal_to_summary(g) for g in mission_goals],
        "goal_count": len(mission_goals),
        "week_start": mission.week_start.isoformat(),
        "week_end": mission.week_end.isoformat(),
        "status": mission.status,
        "xp_reward": mission.xp_reward,
        "weekly_target": mission.weekly_target,
        "coaching_message": mission.coaching_message,
        "workouts": [workout_to_response(w) for w in mission.workouts],
        "workouts_completed": workouts_completed,
        "workouts_total": len(mission.workouts),
        "days_remaining": days_until(mission.week_end)
    }


def mission_to_summary(mission: WeeklyMission) -> Dict[str, Any]:
    """Convert WeeklyMission to summary dict"""
    # Get goals from junction table or legacy single goal
    # Handle case where mission_goals table doesn't exist yet
    try:
        mission_goals = [mg.goal for mg in mission.mission_goals if mg.goal] if mission.mission_goals else []
    except (OperationalError, ProgrammingError, Exception) as e:
        logger.warning(f"Failed to access mission_goals: {e}. Using legacy goal.")
        mission_goals = []

    if not mission_goals and mission.goal:
        mission_goals = [mission.goal]

    primary_goal = mission_goals[0] if mission_goals else mission.goal
    workouts_completed = sum(1 for w in mission.workouts if w.status == MissionWorkoutStatus.COMPLETED.value)

    return {
        "id": mission.id,
        "goal_exercise_name": primary_goal.exercise.name if primary_goal and primary_goal.exercise else "Unknown",
        "goal_target_weight": primary_goal.target_weight if primary_goal else 0,
        "goal_weight_unit": primary_goal.weight_unit if primary_goal else "lb",
        "training_split": mission.training_split,
        "goals": [goal_to_summary(g) for g in mission_goals],
        "goal_count": len(mission_goals),
        "status": mission.status,
        "week_start": mission.week_start.isoformat(),
        "week_end": mission.week_end.isoformat(),
        "xp_reward": mission.xp_reward,
        "workouts_completed": workouts_completed,
        "workouts_total": len(mission.workouts),
        "days_remaining": days_until(mission.week_end),
        "workouts": [workout_to_summary(w) for w in mission.workouts]
    }


def workout_to_response(workout: MissionWorkout) -> Dict[str, Any]:
    """Convert MissionWorkout to response dict"""
    return {
        "id": workout.id,
        "day_number": workout.day_number,
        "focus": workout.focus,
        "primary_lift": workout.primary_lift,
        "status": workout.status,
        "completed_workout_id": workout.completed_workout_id,
        "completed_at": to_iso8601_utc(workout.completed_at) if workout.completed_at else None,
        "prescriptions": [prescription_to_response(p) for p in workout.prescriptions]
    }


def workout_to_summary(workout: MissionWorkout) -> Dict[str, Any]:
    """Convert MissionWorkout to summary dict"""
    return {
        "id": workout.id,
        "day_number": workout.day_number,
        "focus": workout.focus,
        "status": workout.status,
        "exercise_count": len(workout.prescriptions) if workout.prescriptions else 0
    }


def prescription_to_response(prescription: ExercisePrescription) -> Dict[str, Any]:
    """Convert ExercisePrescription to response dict"""
    return {
        "id": prescription.id,
        "exercise_id": prescription.exercise_id,
        "exercise_name": prescription.exercise.name if prescription.exercise else "Unknown",
        "order_index": prescription.order_index,
        "sets": prescription.sets,
        "reps": prescription.reps,
        "weight": prescription.weight,
        "weight_unit": prescription.weight_unit,
        "rpe_target": prescription.rpe_target,
        "notes": prescription.notes,
        "is_completed": prescription.is_completed
    }


# ============ Quest Integration ============

def get_active_mission_for_quests(db: Session, user_id: str) -> Optional[WeeklyMission]:
    """
    Get the user's active mission if they have one.
    Used by quest service to determine if quests should be replaced.
    """
    return db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts),
        joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
    ).filter(
        WeeklyMission.user_id == user_id,
        WeeklyMission.status == MissionStatus.ACCEPTED.value
    ).first()


def format_mission_as_quests(mission: WeeklyMission) -> List[Dict[str, Any]]:
    """
    Format mission workouts as quest-like objects.
    Used when replacing daily quests with mission objectives.
    """
    quests = []

    for workout in mission.workouts:
        quest = {
            "id": f"mission_{workout.id}",
            "quest_id": f"mission_workout_{workout.day_number}",
            "name": workout.focus,
            "description": f"Complete {workout.focus} workout",
            "quest_type": "mission_workout",
            "target_value": 1,
            "xp_reward": mission.xp_reward // len(mission.workouts),
            "progress": 1 if workout.status == MissionWorkoutStatus.COMPLETED.value else 0,
            "is_completed": workout.status == MissionWorkoutStatus.COMPLETED.value,
            "is_claimed": False,  # Mission rewards claimed all at once
            "difficulty": "normal",
            "is_mission_objective": True,
            "mission_id": mission.id
        }
        quests.append(quest)

    return quests
