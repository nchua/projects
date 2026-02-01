"""
XP Calculation and Leveling Service
Handles XP awards, level progression, and rank advancement
"""
from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import Optional, Dict, List, Any, Union
from app.models.progress import UserProgress, HunterRank
from app.models.workout import WorkoutSession, WorkoutExercise, Set
from app.core.utils import to_iso8601_utc


def to_date(value: Union[date, Any]) -> date:
    """Convert a datetime or date object to a date object."""
    return value.date() if hasattr(value, 'date') else value


# XP Reward Constants
XP_REWARDS = {
    "workout_complete": 50,       # Base XP per workout
    "volume_bonus_per_1000lb": 5, # XP per 1000 lbs of volume
    "pr_achieved": 100,           # Personal record bonus
    "first_workout_today": 25,    # First workout of the day bonus
    "big_three_set": 3,           # Bonus per Squat/Bench/Deadlift working set
    "streak_7_day": 150,          # 7-day streak bonus
    "streak_30_day": 500,         # 30-day streak bonus
}

# Big Three exercise canonical names (lowercase for matching)
BIG_THREE = ["back squat", "bench press", "deadlift"]

# Level formula: XP needed to reach next level
def xp_for_level(level: int) -> int:
    """Calculate total XP needed to reach a given level"""
    return int(100 * (level ** 1.5))

def xp_to_next_level(current_level: int, current_xp: int) -> int:
    """Calculate XP remaining to reach next level"""
    return xp_for_level(current_level + 1) - current_xp

def level_progress(current_level: int, current_xp: int) -> float:
    """Calculate progress percentage toward next level (0.0 - 1.0)"""
    xp_for_current = xp_for_level(current_level)
    xp_for_next = xp_for_level(current_level + 1)
    xp_in_level = current_xp - xp_for_current
    xp_needed = xp_for_next - xp_for_current
    return min(1.0, max(0.0, xp_in_level / xp_needed))

# Rank thresholds (level ranges)
RANK_THRESHOLDS = {
    HunterRank.E: (1, 10),
    HunterRank.D: (11, 25),
    HunterRank.C: (26, 45),
    HunterRank.B: (46, 70),
    HunterRank.A: (71, 90),
    HunterRank.S: (91, 999),
}

def get_rank_for_level(level: int) -> str:
    """Determine hunter rank based on level"""
    for rank, (min_level, max_level) in RANK_THRESHOLDS.items():
        if min_level <= level <= max_level:
            return rank.value
    return HunterRank.S.value


def get_or_create_user_progress(db: Session, user_id: str) -> UserProgress:
    """Get existing user progress or create new one"""
    progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
    if not progress:
        progress = UserProgress(user_id=user_id)
        db.add(progress)
        db.flush()
    return progress


def calculate_workout_xp(
    db: Session,
    workout: WorkoutSession,
    prs_achieved: int = 0
) -> Dict[str, Any]:
    """
    Calculate XP earned from a completed workout

    Args:
        db: Database session
        workout: The completed workout session
        prs_achieved: Number of PRs set during this workout

    Returns:
        Dict with xp_earned, breakdown, and any bonuses
    """
    breakdown = {}

    # Base XP for completing workout
    breakdown["workout_complete"] = XP_REWARDS["workout_complete"]

    # Calculate total volume
    total_volume = 0
    big_three_sets = 0

    for workout_exercise in workout.workout_exercises:
        exercise_name = workout_exercise.exercise.name.lower() if workout_exercise.exercise else ""

        for set_obj in workout_exercise.sets:
            # Add to volume (weight * reps)
            set_volume = set_obj.weight * set_obj.reps
            total_volume += set_volume

            # Count Big Three working sets (non-warmup)
            if any(bt in exercise_name for bt in BIG_THREE):
                # Assuming sets with RPE >= 6 or weight > 50% of max are working sets
                if set_obj.rpe is None or set_obj.rpe >= 6:
                    big_three_sets += 1

    # Volume bonus (per 1000 lbs)
    volume_bonus = int(total_volume / 1000) * XP_REWARDS["volume_bonus_per_1000lb"]
    if volume_bonus > 0:
        breakdown["volume_bonus"] = volume_bonus

    # Big Three bonus
    big_three_bonus = big_three_sets * XP_REWARDS["big_three_set"]
    if big_three_bonus > 0:
        breakdown["big_three_bonus"] = big_three_bonus

    # PR bonus
    if prs_achieved > 0:
        breakdown["pr_bonus"] = prs_achieved * XP_REWARDS["pr_achieved"]

    # Calculate total
    total_xp = sum(breakdown.values())

    return {
        "xp_earned": total_xp,
        "breakdown": breakdown,
        "total_volume": int(total_volume),
        "big_three_sets": big_three_sets,
        "prs_achieved": prs_achieved
    }


def award_xp(
    db: Session,
    user_id: str,
    xp_amount: int,
    workout_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Award XP to user and handle level/rank progression

    Args:
        db: Database session
        user_id: User ID
        xp_amount: Amount of XP to award
        workout_date: Date of workout for streak tracking

    Returns:
        Dict with new totals, level up info, rank up info
    """
    progress = get_or_create_user_progress(db, user_id)

    old_level = progress.level
    old_rank = progress.rank
    old_xp = progress.total_xp

    # Award XP
    progress.total_xp += xp_amount

    # Check for level ups
    levels_gained = 0
    while progress.total_xp >= xp_for_level(progress.level + 1):
        progress.level += 1
        levels_gained += 1

    # Update rank if needed
    new_rank = get_rank_for_level(progress.level)
    rank_changed = new_rank != old_rank
    if rank_changed:
        progress.rank = new_rank

    # Handle streak tracking
    streak_bonus = 0
    if workout_date:
        today = to_date(workout_date)

        if progress.last_workout_date:
            last_date = to_date(progress.last_workout_date)
            days_since = (today - last_date).days

            if days_since == 1:
                # Consecutive day - extend streak
                progress.current_streak += 1

                # Check for streak milestones
                if progress.current_streak == 7:
                    streak_bonus = XP_REWARDS["streak_7_day"]
                elif progress.current_streak == 30:
                    streak_bonus = XP_REWARDS["streak_30_day"]
                elif progress.current_streak % 7 == 0:
                    # Weekly streak bonus
                    streak_bonus = XP_REWARDS["streak_7_day"] // 2

            elif days_since > 1:
                # Streak broken
                progress.current_streak = 1
            # days_since == 0 means same day, streak unchanged
        else:
            # First workout
            progress.current_streak = 1

        # Update longest streak
        if progress.current_streak > progress.longest_streak:
            progress.longest_streak = progress.current_streak

        progress.last_workout_date = today

    # Award streak bonus XP if earned
    if streak_bonus > 0:
        progress.total_xp += streak_bonus
        # Re-check for level ups after streak bonus
        while progress.total_xp >= xp_for_level(progress.level + 1):
            progress.level += 1
            levels_gained += 1

    # Update workout count
    progress.total_workouts += 1

    db.flush()

    return {
        "xp_earned": xp_amount,
        "streak_bonus": streak_bonus,
        "total_xp": progress.total_xp,
        "old_level": old_level,
        "new_level": progress.level,
        "leveled_up": levels_gained > 0,
        "levels_gained": levels_gained,
        "old_rank": old_rank,
        "new_rank": progress.rank,
        "rank_changed": rank_changed,
        "current_streak": progress.current_streak,
        "xp_to_next_level": xp_to_next_level(progress.level, progress.total_xp),
        "level_progress": level_progress(progress.level, progress.total_xp)
    }


def get_user_progress_summary(db: Session, user_id: str) -> Dict[str, Any]:
    """Get user's current progress summary for display"""
    progress = get_or_create_user_progress(db, user_id)

    return {
        "total_xp": progress.total_xp,
        "level": progress.level,
        "rank": progress.rank,
        "current_streak": progress.current_streak,
        "longest_streak": progress.longest_streak,
        "total_workouts": progress.total_workouts,
        "total_volume_lb": progress.total_volume_lb,
        "total_prs": progress.total_prs,
        "xp_to_next_level": xp_to_next_level(progress.level, progress.total_xp),
        "level_progress": level_progress(progress.level, progress.total_xp),
        "last_workout_date": to_iso8601_utc(progress.last_workout_date)
    }
