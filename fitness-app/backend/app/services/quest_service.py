"""
Quest Service - Daily quest generation, progress tracking, and rewards
"""
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any
import random
import uuid

from sqlalchemy.orm import joinedload
from app.models.quest import QuestDefinition, UserQuest
from app.models.workout import WorkoutSession, WorkoutExercise
from app.services.xp_service import award_xp, get_or_create_user_progress
from app.core.utils import to_iso8601_utc


# Compound exercises for quest checking (lowercase for matching)
COMPOUND_EXERCISES = [
    "back squat", "squat", "front squat",
    "bench press", "flat bench", "incline bench",
    "deadlift", "conventional deadlift", "sumo deadlift", "romanian deadlift",
    "overhead press", "shoulder press", "military press",
    "barbell row", "bent over row", "pendlay row"
]


def get_midnight_utc_tomorrow() -> datetime:
    """Get the next midnight UTC"""
    now = datetime.now(timezone.utc)
    tomorrow = now.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=timezone.utc)


def calculate_todays_workout_stats(db: Session, user_id: str, target_date: date) -> Dict[str, Any]:
    """
    Calculate aggregate stats from workouts for a specific date's quests.

    Only workouts matching the exact target_date are included. Earlier workouts
    from the week do NOT count toward daily quests.

    Args:
        db: Database session
        user_id: User ID
        target_date: The specific date to calculate stats for

    Returns:
        Dict with total_reps, compound_sets, total_volume, and workout_count
    """
    # Get workouts with their exercises and sets
    workouts = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.deleted_at == None
    ).all()

    # Filter to ONLY workouts matching the exact target date
    # A Feb 1 quest only counts Feb 1 workouts, not Jan 31 or earlier
    matching_workouts = []
    for w in workouts:
        workout_date = w.date.date() if hasattr(w.date, 'date') else w.date
        if workout_date == target_date:
            matching_workouts.append(w)

    total_reps = 0
    compound_sets = 0
    total_volume = 0

    for workout in matching_workouts:
        for workout_exercise in workout.workout_exercises:
            exercise_name = workout_exercise.exercise.name.lower() if workout_exercise.exercise else ""

            for set_obj in workout_exercise.sets:
                total_reps += set_obj.reps
                total_volume += set_obj.weight * set_obj.reps

                if any(compound in exercise_name for compound in COMPOUND_EXERCISES):
                    compound_sets += 1

    return {
        "total_reps": total_reps,
        "compound_sets": compound_sets,
        "total_volume": int(total_volume),
        "workout_count": len(matching_workouts)
    }


def get_today_utc() -> date:
    """Get today's date in UTC"""
    return datetime.now(timezone.utc).date()


def get_daily_quests(db: Session, user_id: str) -> Dict[str, Any]:
    """
    Get today's daily quests for a user. Generate new ones if needed.
    Recalculates progress from all workouts logged today.

    If the user has an active weekly mission, returns mission objectives
    instead of regular daily quests.

    Returns:
        Dict with quests list, refresh timestamp, and counts
    """
    # Check for active mission first
    from app.services.mission_service import get_active_mission_for_quests, format_mission_as_quests

    active_mission = get_active_mission_for_quests(db, user_id)
    if active_mission:
        # Return mission objectives as quests
        mission_quests = format_mission_as_quests(active_mission)
        completed_count = sum(1 for q in mission_quests if q["is_completed"])

        return {
            "quests": mission_quests,
            "refresh_at": to_iso8601_utc(get_midnight_utc_tomorrow()),
            "completed_count": completed_count,
            "total_count": len(mission_quests),
            "is_mission_mode": True,
            "mission_id": active_mission.id
        }

    today = get_today_utc()

    # Check for existing quests assigned today
    user_quests = db.query(UserQuest).filter(
        UserQuest.user_id == user_id,
        UserQuest.assigned_date == today
    ).all()

    # If no quests for today, generate new ones
    if not user_quests:
        user_quests = generate_daily_quests(db, user_id)

    # Recalculate progress from all today's workouts for unclaimed quests
    # This ensures progress is accurate even if workouts were logged before quests existed
    unclaimed_quests = [uq for uq in user_quests if not uq.is_claimed]
    if unclaimed_quests:
        recalculate_quest_progress(db, user_id, unclaimed_quests, today)

    # Build response
    quests = []
    completed_count = 0

    for uq in user_quests:
        quest_def = uq.quest
        quests.append({
            "id": uq.id,
            "quest_id": quest_def.id,
            "name": quest_def.name,
            "description": quest_def.description,
            "quest_type": quest_def.quest_type,
            "target_value": quest_def.target_value,
            "xp_reward": quest_def.xp_reward,
            "progress": uq.progress,
            "is_completed": uq.is_completed,
            "is_claimed": uq.is_claimed,
            "difficulty": quest_def.difficulty,
            "completed_by_workout_id": uq.completed_by_workout_id if hasattr(uq, 'completed_by_workout_id') else None
        })
        if uq.is_completed:
            completed_count += 1

    return {
        "quests": quests,
        "refresh_at": to_iso8601_utc(get_midnight_utc_tomorrow()),
        "completed_count": completed_count,
        "total_count": len(quests),
        "is_mission_mode": False,
        "mission_id": None
    }


def generate_daily_quests(db: Session, user_id: str, count: int = 3) -> List[UserQuest]:
    """
    Generate new daily quests for a user.
    Picks one quest from each difficulty (easy, normal, hard) if available.
    """
    today = get_today_utc()

    # Get all active daily quest definitions (excluding duration-based quests)
    quest_defs = db.query(QuestDefinition).filter(
        QuestDefinition.is_daily == True,
        QuestDefinition.is_active == True,
        QuestDefinition.quest_type != "workout_duration"  # Exclude speed-based quests
    ).all()

    if not quest_defs:
        return []

    # Group by difficulty
    by_difficulty = {"easy": [], "normal": [], "hard": []}
    for qd in quest_defs:
        if qd.difficulty in by_difficulty:
            by_difficulty[qd.difficulty].append(qd)

    # Select one from each difficulty
    selected_quests = []
    for difficulty in ["easy", "normal", "hard"]:
        if by_difficulty[difficulty]:
            selected_quests.append(random.choice(by_difficulty[difficulty]))

    # If we don't have 3 yet, pick more randomly
    while len(selected_quests) < count and quest_defs:
        remaining = [q for q in quest_defs if q not in selected_quests]
        if remaining:
            selected_quests.append(random.choice(remaining))
        else:
            break

    # Create UserQuest records
    user_quests = []
    for quest_def in selected_quests:
        user_quest = UserQuest(
            id=str(uuid.uuid4()),
            user_id=user_id,
            quest_id=quest_def.id,
            assigned_date=today,
            progress=0,
            is_completed=False,
            is_claimed=False
        )
        db.add(user_quest)
        user_quests.append(user_quest)

    db.flush()
    return user_quests


def recalculate_quest_progress(db: Session, user_id: str, user_quests: List[UserQuest], today: date) -> List[str]:
    """
    Recalculate quest progress based on ALL workouts logged today.
    This ensures progress is accurate even if workouts were logged before quests existed.

    Args:
        db: Database session
        user_id: User ID
        user_quests: List of UserQuest objects to update
        today: Today's date

    Returns:
        List of quest IDs that are now completed
    """
    # Get aggregate stats from all today's workouts
    stats = calculate_todays_workout_stats(db, user_id, today)

    if stats["workout_count"] == 0:
        return []

    completed_quest_ids = []

    for uq in user_quests:
        if uq.is_claimed:
            continue  # Don't update claimed quests

        quest_def = uq.quest
        progress = 0

        if quest_def.quest_type == "total_reps":
            progress = stats["total_reps"]
        elif quest_def.quest_type == "compound_sets":
            progress = stats["compound_sets"]
        elif quest_def.quest_type == "total_volume":
            progress = stats["total_volume"]
        # Note: workout_duration quests have been removed

        # Update progress (don't exceed target)
        uq.progress = min(progress, quest_def.target_value)

        # Check if quest is now completed
        if uq.progress >= quest_def.target_value and not uq.is_completed:
            uq.is_completed = True
            uq.completed_at = datetime.utcnow()
            completed_quest_ids.append(uq.id)

    db.flush()
    return completed_quest_ids


def update_quest_progress(db: Session, user_id: str, workout: WorkoutSession) -> List[str]:
    """
    Update quest progress based on a completed workout.

    The workout's LOCAL date determines which quests are affected. This ensures
    a workout logged for "Jan 31" affects "Jan 31" quests, even if the current
    UTC date is "Feb 1".

    Args:
        db: Database session
        user_id: User ID
        workout: The completed workout session

    Returns:
        List of quest IDs that were completed by this workout
    """
    # Use the workout's date to find matching quests
    # Workout dates are LOCAL dates (the day the user worked out in their timezone)
    workout_date = workout.date.date() if hasattr(workout.date, 'date') else workout.date
    today_utc = get_today_utc()

    # Get quests for the workout's date
    user_quests = db.query(UserQuest).filter(
        UserQuest.user_id == user_id,
        UserQuest.assigned_date == workout_date,
        UserQuest.is_claimed == False
    ).all()

    # If no quests exist for the workout's date and it matches today (UTC),
    # generate new quests. Only generate for today, not past dates.
    if not user_quests and workout_date == today_utc:
        # Check if any quests exist at all for today (including claimed ones)
        any_quests_today = db.query(UserQuest).filter(
            UserQuest.user_id == user_id,
            UserQuest.assigned_date == workout_date
        ).first()

        # Only generate if no quests exist for today (not if all were claimed)
        if not any_quests_today:
            user_quests = generate_daily_quests(db, user_id)

        # If still no unclaimed quests, return early
        if not user_quests:
            return []

    # Calculate workout stats for quest checking
    total_reps = 0
    compound_sets = 0
    total_volume = 0

    for workout_exercise in workout.workout_exercises:
        exercise_name = workout_exercise.exercise.name.lower() if workout_exercise.exercise else ""

        for set_obj in workout_exercise.sets:
            # Total reps
            total_reps += set_obj.reps

            # Total volume (weight * reps)
            total_volume += set_obj.weight * set_obj.reps

            # Count compound sets
            if any(compound in exercise_name for compound in COMPOUND_EXERCISES):
                compound_sets += 1

    # Update each quest's progress
    completed_quest_ids = []

    for uq in user_quests:
        quest_def = uq.quest
        progress = 0

        if quest_def.quest_type == "total_reps":
            progress = total_reps
        elif quest_def.quest_type == "compound_sets":
            progress = compound_sets
        elif quest_def.quest_type == "total_volume":
            progress = int(total_volume)
        # Note: workout_duration quests have been removed

        # Update progress (don't exceed target)
        uq.progress = min(progress, quest_def.target_value)

        # Check if quest is now completed
        if uq.progress >= quest_def.target_value and not uq.is_completed:
            uq.is_completed = True
            uq.completed_at = datetime.utcnow()
            # TODO: Re-enable after migration runs
            # uq.completed_by_workout_id = workout.id
            completed_quest_ids.append(uq.id)

    db.flush()
    return completed_quest_ids


def claim_quest_reward(db: Session, user_id: str, user_quest_id: str) -> Dict[str, Any]:
    """
    Claim XP reward for a completed quest.

    Args:
        db: Database session
        user_id: User ID
        user_quest_id: UserQuest ID to claim

    Returns:
        Dict with XP earned, new totals, level up info

    Raises:
        ValueError: If quest not found, not completed, or already claimed
    """
    user_quest = db.query(UserQuest).filter(
        UserQuest.id == user_quest_id,
        UserQuest.user_id == user_id
    ).first()

    if not user_quest:
        raise ValueError("Quest not found")

    if not user_quest.is_completed:
        raise ValueError("Quest not completed yet")

    if user_quest.is_claimed:
        raise ValueError("Quest already claimed")

    # Get XP reward from quest definition
    quest_def = user_quest.quest
    xp_reward = quest_def.xp_reward

    # Award XP
    progress = get_or_create_user_progress(db, user_id)
    old_level = progress.level
    old_rank = progress.rank

    progress.total_xp += xp_reward

    # Check for level ups
    from app.services.xp_service import xp_for_level, get_rank_for_level

    while progress.total_xp >= xp_for_level(progress.level + 1):
        progress.level += 1

    # Update rank if needed
    new_rank = get_rank_for_level(progress.level)
    rank_changed = new_rank != old_rank
    if rank_changed:
        progress.rank = new_rank

    # Mark quest as claimed
    user_quest.is_claimed = True
    user_quest.claimed_at = datetime.utcnow()

    db.flush()

    return {
        "success": True,
        "xp_earned": xp_reward,
        "total_xp": progress.total_xp,
        "level": progress.level,
        "leveled_up": progress.level > old_level,
        "new_level": progress.level if progress.level > old_level else None,
        "rank": progress.rank,
        "rank_changed": rank_changed,
        "new_rank": progress.rank if rank_changed else None
    }


def seed_quest_definitions(db: Session) -> int:
    """
    Seed the database with quest definitions.

    Returns:
        Number of quests created
    """
    quest_definitions = [
        # Rep-based quests
        {"id": "reps_50", "name": "Rep It Out", "description": "Complete 50 total reps",
         "quest_type": "total_reps", "target_value": 50, "xp_reward": 15, "difficulty": "easy"},
        {"id": "reps_100", "name": "Century Club", "description": "Complete 100 total reps",
         "quest_type": "total_reps", "target_value": 100, "xp_reward": 25, "difficulty": "normal"},
        {"id": "reps_150", "name": "Rep Warrior", "description": "Complete 150 total reps",
         "quest_type": "total_reps", "target_value": 150, "xp_reward": 35, "difficulty": "normal"},
        {"id": "reps_200", "name": "Rep Machine", "description": "Complete 200 total reps",
         "quest_type": "total_reps", "target_value": 200, "xp_reward": 50, "difficulty": "hard"},

        # Compound lift quests
        {"id": "compound_3", "name": "Foundation Builder", "description": "Do 3 sets of compound lifts",
         "quest_type": "compound_sets", "target_value": 3, "xp_reward": 20, "difficulty": "easy"},
        {"id": "compound_5", "name": "Compound Focus", "description": "Do 5 sets of compound lifts",
         "quest_type": "compound_sets", "target_value": 5, "xp_reward": 30, "difficulty": "normal"},
        {"id": "compound_8", "name": "Strength Builder", "description": "Do 8 sets of compound lifts",
         "quest_type": "compound_sets", "target_value": 8, "xp_reward": 45, "difficulty": "normal"},
        {"id": "compound_12", "name": "Powerhouse", "description": "Do 12 sets of compound lifts",
         "quest_type": "compound_sets", "target_value": 12, "xp_reward": 60, "difficulty": "hard"},

        # Volume-based quests
        {"id": "volume_3k", "name": "Volume Starter", "description": "Lift 3,000 lbs total",
         "quest_type": "total_volume", "target_value": 3000, "xp_reward": 15, "difficulty": "easy"},
        {"id": "volume_5k", "name": "Volume Builder", "description": "Lift 5,000 lbs total",
         "quest_type": "total_volume", "target_value": 5000, "xp_reward": 25, "difficulty": "easy"},
        {"id": "volume_10k", "name": "Heavy Lifter", "description": "Lift 10,000 lbs total",
         "quest_type": "total_volume", "target_value": 10000, "xp_reward": 40, "difficulty": "normal"},
        {"id": "volume_15k", "name": "Volume Warrior", "description": "Lift 15,000 lbs total",
         "quest_type": "total_volume", "target_value": 15000, "xp_reward": 55, "difficulty": "normal"},
        {"id": "volume_20k", "name": "Tonnage King", "description": "Lift 20,000 lbs total",
         "quest_type": "total_volume", "target_value": 20000, "xp_reward": 70, "difficulty": "hard"},
    ]

    created_count = 0
    for quest_data in quest_definitions:
        # Check if quest already exists
        existing = db.query(QuestDefinition).filter(QuestDefinition.id == quest_data["id"]).first()
        if not existing:
            quest = QuestDefinition(
                id=quest_data["id"],
                name=quest_data["name"],
                description=quest_data["description"],
                quest_type=quest_data["quest_type"],
                target_value=quest_data["target_value"],
                xp_reward=quest_data["xp_reward"],
                difficulty=quest_data["difficulty"],
                is_daily=True,
                is_active=True
            )
            db.add(quest)
            created_count += 1

    db.commit()
    return created_count
