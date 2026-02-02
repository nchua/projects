"""
Mission Service - Goals, weekly missions, and AI-powered coaching
"""
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any
import uuid

from app.models.mission import (
    Goal, WeeklyMission, MissionWorkout, ExercisePrescription,
    GoalStatus, MissionStatus, MissionWorkoutStatus
)
from app.models.workout import WorkoutSession, WorkoutExercise
from app.models.exercise import Exercise
from app.models.pr import PR
from app.core.utils import to_iso8601_utc


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


# ============ Goal Functions ============

def create_goal(
    db: Session,
    user_id: str,
    exercise_id: str,
    target_weight: float,
    weight_unit: str,
    deadline: date,
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
    weight_unit: Optional[str] = None,
    deadline: Optional[date] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None
) -> Goal:
    """Update an existing goal"""
    if target_weight is not None:
        goal.target_weight = target_weight
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


def update_goal_progress(db: Session, user_id: str, exercise_id: str, new_e1rm: float) -> List[str]:
    """
    Update progress on goals when a new e1RM is achieved.

    Args:
        db: Database session
        user_id: User ID
        exercise_id: Exercise that was performed
        new_e1rm: New estimated 1RM

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

        # Check if goal is achieved
        if new_e1rm >= goal.target_weight and goal.status == GoalStatus.ACTIVE.value:
            goal.status = GoalStatus.COMPLETED.value
            goal.achieved_at = datetime.utcnow()
            completed_goal_ids.append(goal.id)

    db.flush()
    return completed_goal_ids


def calculate_goal_progress(goal: Goal) -> Dict[str, Any]:
    """Calculate progress metrics for a goal"""
    current = goal.current_e1rm or goal.starting_e1rm or 0
    target = goal.target_weight

    if target > 0:
        progress_percent = min(100, (current / target) * 100)
    else:
        progress_percent = 0

    weight_to_go = max(0, target - current)

    return {
        "progress_percent": round(progress_percent, 1),
        "weight_to_go": weight_to_go,
        "weeks_remaining": weeks_until(goal.deadline)
    }


def goal_to_response(goal: Goal) -> Dict[str, Any]:
    """Convert Goal model to response dict"""
    progress = calculate_goal_progress(goal)

    return {
        "id": goal.id,
        "exercise_id": goal.exercise_id,
        "exercise_name": goal.exercise.name if goal.exercise else "Unknown",
        "target_weight": goal.target_weight,
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

    return {
        "id": goal.id,
        "exercise_name": goal.exercise.name if goal.exercise else "Unknown",
        "target_weight": goal.target_weight,
        "weight_unit": goal.weight_unit,
        "deadline": goal.deadline.isoformat(),
        "progress_percent": progress["progress_percent"],
        "status": goal.status
    }


# ============ Mission Functions ============

def get_or_create_current_mission(db: Session, user_id: str) -> Dict[str, Any]:
    """
    Get the current week's mission, or generate one if needed.

    Returns a dict with:
    - has_active_goal: bool
    - goal: GoalSummary or None
    - mission: MissionSummary or None
    - needs_goal_setup: bool
    """
    # Check for active goals
    active_goals = get_user_goals(db, user_id, include_inactive=False)

    if not active_goals:
        return {
            "has_active_goal": False,
            "goal": None,
            "mission": None,
            "needs_goal_setup": True
        }

    # Use the first active goal (could later support multiple)
    primary_goal = active_goals[0]

    # Get week boundaries
    today = get_today_utc()
    week_start, week_end = get_week_boundaries(today)

    # Check for existing mission this week
    mission = db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions),
        joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
    ).filter(
        WeeklyMission.user_id == user_id,
        WeeklyMission.goal_id == primary_goal.id,
        WeeklyMission.week_start == week_start
    ).first()

    # If no mission exists and it's Sunday or Monday, create one
    if not mission:
        # Only auto-generate on Sunday (6) or Monday (0)
        if today.weekday() in [0, 6]:
            mission = generate_weekly_mission(db, user_id, primary_goal, week_start, week_end)
        else:
            # Mid-week with no mission - they can still create goals
            return {
                "has_active_goal": True,
                "goal": goal_to_summary(primary_goal),
                "mission": None,
                "needs_goal_setup": False
            }

    return {
        "has_active_goal": True,
        "goal": goal_to_summary(primary_goal),
        "mission": mission_to_summary(mission) if mission else None,
        "needs_goal_setup": False
    }


def generate_weekly_mission(
    db: Session,
    user_id: str,
    goal: Goal,
    week_start: date,
    week_end: date
) -> WeeklyMission:
    """
    Generate a weekly mission based on a goal.

    For MVP, generates 3 workouts with basic structure.
    Later phases will use AI to customize.
    """
    mission = WeeklyMission(
        id=str(uuid.uuid4()),
        user_id=user_id,
        goal_id=goal.id,
        week_start=week_start,
        week_end=week_end,
        status=MissionStatus.OFFERED.value,
        xp_reward=200,
        weekly_target=f"Focus on {goal.exercise.name if goal.exercise else 'your goal lift'}",
        coaching_message="Complete these workouts this week to progress toward your goal!"
    )

    db.add(mission)
    db.flush()

    # Generate 3 workouts
    workout_templates = [
        {"day": 1, "focus": f"Heavy {goal.exercise.name if goal.exercise else 'Main Lift'}", "primary_lift": goal.exercise.name if goal.exercise else None},
        {"day": 2, "focus": "Accessory Work", "primary_lift": None},
        {"day": 3, "focus": f"Volume {goal.exercise.name if goal.exercise else 'Main Lift'}", "primary_lift": goal.exercise.name if goal.exercise else None},
    ]

    for template in workout_templates:
        workout = MissionWorkout(
            id=str(uuid.uuid4()),
            mission_id=mission.id,
            day_number=template["day"],
            focus=template["focus"],
            primary_lift=template["primary_lift"],
            status=MissionWorkoutStatus.PENDING.value
        )
        db.add(workout)
        db.flush()

        # Add exercise prescriptions for workouts with the goal exercise
        if template["primary_lift"] and goal.exercise_id:
            # Main lift prescription
            if template["day"] == 1:
                # Heavy day: 4x5
                sets, reps = 4, 5
            else:
                # Volume day: 3x10
                sets, reps = 3, 10

            prescription = ExercisePrescription(
                id=str(uuid.uuid4()),
                mission_workout_id=workout.id,
                exercise_id=goal.exercise_id,
                order_index=0,
                sets=sets,
                reps=reps,
                weight=None,  # User can input their own weight
                weight_unit=goal.weight_unit,
                notes="Focus on form and progressive overload"
            )
            db.add(prescription)

    db.flush()

    # Reload with relationships
    mission = db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions).joinedload(ExercisePrescription.exercise),
        joinedload(WeeklyMission.goal).joinedload(Goal.exercise)
    ).filter(WeeklyMission.id == mission.id).first()

    return mission


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

    For MVP, uses simple matching: if workout has the goal exercise, it counts.
    Later phases will use AI to evaluate exercise equivalence.

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
        "xp_earned": 0
    }

    # Get active missions
    active_missions = db.query(WeeklyMission).options(
        joinedload(WeeklyMission.workouts).joinedload(MissionWorkout.prescriptions),
        joinedload(WeeklyMission.goal)
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
        mission_goal_exercise_id = mission.goal.exercise_id if mission.goal else None

        for mission_workout in mission.workouts:
            if mission_workout.status != MissionWorkoutStatus.PENDING.value:
                continue

            # For MVP: Check if logged workout includes the goal exercise
            if mission_goal_exercise_id and mission_goal_exercise_id in logged_exercise_ids:
                # Mark this mission workout as completed
                mission_workout.status = MissionWorkoutStatus.COMPLETED.value
                mission_workout.completed_workout_id = workout.id
                mission_workout.completed_at = datetime.utcnow()
                mission_workout.completion_notes = "Workout included the goal exercise"

                result["mission_workouts_completed"].append({
                    "id": mission_workout.id,
                    "focus": mission_workout.focus,
                    "day_number": mission_workout.day_number
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
                "xp_reward": mission.xp_reward
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
    goal = mission.goal
    workouts_completed = sum(1 for w in mission.workouts if w.status == MissionWorkoutStatus.COMPLETED.value)

    return {
        "id": mission.id,
        "goal_id": mission.goal_id,
        "goal_exercise_name": goal.exercise.name if goal and goal.exercise else "Unknown",
        "goal_target_weight": goal.target_weight if goal else 0,
        "goal_weight_unit": goal.weight_unit if goal else "lb",
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
    goal = mission.goal
    workouts_completed = sum(1 for w in mission.workouts if w.status == MissionWorkoutStatus.COMPLETED.value)

    return {
        "id": mission.id,
        "goal_exercise_name": goal.exercise.name if goal and goal.exercise else "Unknown",
        "goal_target_weight": goal.target_weight if goal else 0,
        "goal_weight_unit": goal.weight_unit if goal else "lb",
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
