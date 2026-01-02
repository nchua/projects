"""
Achievement Service
Handles achievement checking, unlocking, and management
"""
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.models.progress import UserProgress
from app.models.achievement import AchievementDefinition, UserAchievement
from app.models.workout import WorkoutSession
from app.models.pr import PR


def get_or_create_user_progress(db: Session, user_id: str) -> UserProgress:
    """Get existing user progress or create new one"""
    progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
    if not progress:
        progress = UserProgress(user_id=user_id)
        db.add(progress)
        db.flush()
    return progress


def get_user_achievements(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """Get all achievements with unlock status for a user"""
    progress = get_or_create_user_progress(db, user_id)

    # Get all active achievement definitions
    definitions = db.query(AchievementDefinition).filter(
        AchievementDefinition.is_active == True
    ).order_by(AchievementDefinition.sort_order).all()

    # Get user's unlocked achievements
    unlocked = db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id
    ).all()
    unlocked_ids = {ua.achievement_id: ua.unlocked_at for ua in unlocked}

    achievements = []
    for definition in definitions:
        unlocked_at = unlocked_ids.get(definition.id)
        achievements.append({
            "id": definition.id,
            "name": definition.name,
            "description": definition.description,
            "category": definition.category,
            "icon": definition.icon,
            "xp_reward": definition.xp_reward,
            "rarity": definition.rarity,
            "unlocked": unlocked_at is not None,
            "unlocked_at": unlocked_at.isoformat() if unlocked_at else None
        })

    return achievements


def get_recently_unlocked(db: Session, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Get most recently unlocked achievements"""
    unlocked = db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id
    ).order_by(UserAchievement.unlocked_at.desc()).limit(limit).all()

    achievements = []
    for ua in unlocked:
        achievements.append({
            "id": ua.achievement.id,
            "name": ua.achievement.name,
            "description": ua.achievement.description,
            "category": ua.achievement.category,
            "icon": ua.achievement.icon,
            "xp_reward": ua.achievement.xp_reward,
            "rarity": ua.achievement.rarity,
            "unlocked_at": ua.unlocked_at.isoformat()
        })

    return achievements


def unlock_achievement(
    db: Session,
    user_id: str,
    achievement_id: str
) -> Optional[Dict[str, Any]]:
    """
    Unlock an achievement for a user

    Returns:
        Achievement data if newly unlocked, None if already unlocked
    """
    progress = get_or_create_user_progress(db, user_id)

    # Check if already unlocked
    existing = db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id,
        UserAchievement.achievement_id == achievement_id
    ).first()

    if existing:
        return None

    # Get achievement definition
    definition = db.query(AchievementDefinition).filter(
        AchievementDefinition.id == achievement_id
    ).first()

    if not definition:
        return None

    # Create unlock record
    user_achievement = UserAchievement(
        user_id=user_id,
        user_progress_id=progress.id,
        achievement_id=achievement_id
    )
    db.add(user_achievement)

    # Award XP for achievement
    progress.total_xp += definition.xp_reward

    db.flush()

    return {
        "id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "category": definition.category,
        "icon": definition.icon,
        "xp_reward": definition.xp_reward,
        "rarity": definition.rarity,
        "unlocked_at": user_achievement.unlocked_at.isoformat()
    }


def check_and_unlock_achievements(
    db: Session,
    user_id: str,
    context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Check for and unlock any newly earned achievements

    Args:
        db: Database session
        user_id: User ID
        context: Context data for checking achievements:
            - workout_count: Total workouts completed
            - level: Current level
            - rank: Current rank
            - prs_count: Total PRs achieved
            - current_streak: Current workout streak
            - exercise_prs: Dict of exercise_name -> max weight

    Returns:
        List of newly unlocked achievements
    """
    progress = get_or_create_user_progress(db, user_id)
    newly_unlocked = []

    # Get all active achievements not yet unlocked by this user
    unlocked_ids = db.query(UserAchievement.achievement_id).filter(
        UserAchievement.user_id == user_id
    ).subquery()

    available = db.query(AchievementDefinition).filter(
        AchievementDefinition.is_active == True,
        ~AchievementDefinition.id.in_(unlocked_ids)
    ).all()

    for achievement in available:
        should_unlock = False

        if achievement.requirement_type == "workout_count":
            should_unlock = context.get("workout_count", 0) >= achievement.requirement_value

        elif achievement.requirement_type == "level_reached":
            should_unlock = context.get("level", 1) >= achievement.requirement_value

        elif achievement.requirement_type == "rank_reached":
            rank_order = {"E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "S": 6}
            current_rank_val = rank_order.get(context.get("rank", "E"), 1)
            required_rank_val = rank_order.get(achievement.requirement_value, 1) if isinstance(achievement.requirement_value, str) else achievement.requirement_value
            should_unlock = current_rank_val >= required_rank_val

        elif achievement.requirement_type == "pr_count":
            should_unlock = context.get("prs_count", 0) >= achievement.requirement_value

        elif achievement.requirement_type == "streak_days":
            should_unlock = context.get("current_streak", 0) >= achievement.requirement_value

        elif achievement.requirement_type == "weight_lifted":
            # Exercise-specific weight achievement
            exercise_prs = context.get("exercise_prs", {})
            if achievement.requirement_exercise:
                exercise_max = exercise_prs.get(achievement.requirement_exercise.lower(), 0)
                should_unlock = exercise_max >= achievement.requirement_value

        if should_unlock:
            unlocked = unlock_achievement(db, user_id, achievement.id)
            if unlocked:
                newly_unlocked.append(unlocked)

    return newly_unlocked


def seed_achievement_definitions(db: Session):
    """Seed the database with default achievement definitions"""

    achievements = [
        # Milestone achievements
        {
            "id": "first_workout",
            "name": "First Steps",
            "description": "Complete your first workout",
            "category": "milestone",
            "icon": "figure.walk",
            "xp_reward": 50,
            "rarity": "common",
            "requirement_type": "workout_count",
            "requirement_value": 1,
            "sort_order": 1
        },
        {
            "id": "workout_10",
            "name": "Dedicated",
            "description": "Complete 10 workouts",
            "category": "milestone",
            "icon": "flame.fill",
            "xp_reward": 100,
            "rarity": "common",
            "requirement_type": "workout_count",
            "requirement_value": 10,
            "sort_order": 2
        },
        {
            "id": "workout_25",
            "name": "Committed",
            "description": "Complete 25 workouts",
            "category": "milestone",
            "icon": "star.fill",
            "xp_reward": 200,
            "rarity": "rare",
            "requirement_type": "workout_count",
            "requirement_value": 25,
            "sort_order": 3
        },
        {
            "id": "workout_50",
            "name": "Iron Will",
            "description": "Complete 50 workouts",
            "category": "milestone",
            "icon": "bolt.fill",
            "xp_reward": 350,
            "rarity": "rare",
            "requirement_type": "workout_count",
            "requirement_value": 50,
            "sort_order": 4
        },
        {
            "id": "workout_100",
            "name": "Legendary Hunter",
            "description": "Complete 100 workouts",
            "category": "milestone",
            "icon": "crown.fill",
            "xp_reward": 500,
            "rarity": "legendary",
            "requirement_type": "workout_count",
            "requirement_value": 100,
            "sort_order": 5
        },

        # PR achievements
        {
            "id": "pr_first",
            "name": "Breaking Limits",
            "description": "Set your first personal record",
            "category": "strength",
            "icon": "arrow.up.circle.fill",
            "xp_reward": 75,
            "rarity": "common",
            "requirement_type": "pr_count",
            "requirement_value": 1,
            "sort_order": 10
        },
        {
            "id": "pr_10",
            "name": "Record Breaker",
            "description": "Set 10 personal records",
            "category": "strength",
            "icon": "chart.line.uptrend.xyaxis",
            "xp_reward": 200,
            "rarity": "rare",
            "requirement_type": "pr_count",
            "requirement_value": 10,
            "sort_order": 11
        },

        # Bench Press achievements
        {
            "id": "bench_135",
            "name": "Iron Initiate",
            "description": "Bench press 135 lbs (1 plate)",
            "category": "strength",
            "icon": "dumbbell.fill",
            "xp_reward": 100,
            "rarity": "common",
            "requirement_type": "weight_lifted",
            "requirement_value": 135,
            "requirement_exercise": "bench press",
            "sort_order": 20
        },
        {
            "id": "bench_185",
            "name": "Bench Warrior",
            "description": "Bench press 185 lbs",
            "category": "strength",
            "icon": "dumbbell.fill",
            "xp_reward": 150,
            "rarity": "rare",
            "requirement_type": "weight_lifted",
            "requirement_value": 185,
            "requirement_exercise": "bench press",
            "sort_order": 21
        },
        {
            "id": "bench_225",
            "name": "Bench Baron",
            "description": "Bench press 225 lbs (2 plates)",
            "category": "strength",
            "icon": "dumbbell.fill",
            "xp_reward": 250,
            "rarity": "epic",
            "requirement_type": "weight_lifted",
            "requirement_value": 225,
            "requirement_exercise": "bench press",
            "sort_order": 22
        },

        # Squat achievements
        {
            "id": "squat_135",
            "name": "Squat Starter",
            "description": "Squat 135 lbs (1 plate)",
            "category": "strength",
            "icon": "figure.strengthtraining.traditional",
            "xp_reward": 100,
            "rarity": "common",
            "requirement_type": "weight_lifted",
            "requirement_value": 135,
            "requirement_exercise": "back squat",
            "sort_order": 30
        },
        {
            "id": "squat_225",
            "name": "Squat Soldier",
            "description": "Squat 225 lbs (2 plates)",
            "category": "strength",
            "icon": "figure.strengthtraining.traditional",
            "xp_reward": 200,
            "rarity": "rare",
            "requirement_type": "weight_lifted",
            "requirement_value": 225,
            "requirement_exercise": "back squat",
            "sort_order": 31
        },
        {
            "id": "squat_315",
            "name": "Squat Sovereign",
            "description": "Squat 315 lbs (3 plates)",
            "category": "strength",
            "icon": "figure.strengthtraining.traditional",
            "xp_reward": 350,
            "rarity": "epic",
            "requirement_type": "weight_lifted",
            "requirement_value": 315,
            "requirement_exercise": "back squat",
            "sort_order": 32
        },

        # Deadlift achievements
        {
            "id": "deadlift_135",
            "name": "Deadlift Debut",
            "description": "Deadlift 135 lbs (1 plate)",
            "category": "strength",
            "icon": "figure.cross.training",
            "xp_reward": 100,
            "rarity": "common",
            "requirement_type": "weight_lifted",
            "requirement_value": 135,
            "requirement_exercise": "deadlift",
            "sort_order": 40
        },
        {
            "id": "deadlift_225",
            "name": "Deadlift Disciple",
            "description": "Deadlift 225 lbs (2 plates)",
            "category": "strength",
            "icon": "figure.cross.training",
            "xp_reward": 175,
            "rarity": "rare",
            "requirement_type": "weight_lifted",
            "requirement_value": 225,
            "requirement_exercise": "deadlift",
            "sort_order": 41
        },
        {
            "id": "deadlift_315",
            "name": "Deadlift Destroyer",
            "description": "Deadlift 315 lbs (3 plates)",
            "category": "strength",
            "icon": "figure.cross.training",
            "xp_reward": 250,
            "rarity": "rare",
            "requirement_type": "weight_lifted",
            "requirement_value": 315,
            "requirement_exercise": "deadlift",
            "sort_order": 42
        },
        {
            "id": "deadlift_405",
            "name": "Deadlift Demon",
            "description": "Deadlift 405 lbs (4 plates)",
            "category": "strength",
            "icon": "figure.cross.training",
            "xp_reward": 400,
            "rarity": "epic",
            "requirement_type": "weight_lifted",
            "requirement_value": 405,
            "requirement_exercise": "deadlift",
            "sort_order": 43
        },

        # Progression achievements
        {
            "id": "level_10",
            "name": "Rising Hunter",
            "description": "Reach level 10",
            "category": "progression",
            "icon": "arrow.up.forward",
            "xp_reward": 100,
            "rarity": "common",
            "requirement_type": "level_reached",
            "requirement_value": 10,
            "sort_order": 50
        },
        {
            "id": "level_25",
            "name": "Proven Hunter",
            "description": "Reach level 25",
            "category": "progression",
            "icon": "arrow.up.forward.circle.fill",
            "xp_reward": 200,
            "rarity": "rare",
            "requirement_type": "level_reached",
            "requirement_value": 25,
            "sort_order": 51
        },
        {
            "id": "level_50",
            "name": "Elite Hunter",
            "description": "Reach level 50",
            "category": "progression",
            "icon": "star.circle.fill",
            "xp_reward": 400,
            "rarity": "epic",
            "requirement_type": "level_reached",
            "requirement_value": 50,
            "sort_order": 52
        },

        # Rank achievements
        {
            "id": "rank_d",
            "name": "D-Rank Hunter",
            "description": "Achieve D-Rank",
            "category": "progression",
            "icon": "d.circle.fill",
            "xp_reward": 150,
            "rarity": "common",
            "requirement_type": "rank_reached",
            "requirement_value": 2,
            "sort_order": 60
        },
        {
            "id": "rank_c",
            "name": "C-Rank Hunter",
            "description": "Achieve C-Rank",
            "category": "progression",
            "icon": "c.circle.fill",
            "xp_reward": 250,
            "rarity": "rare",
            "requirement_type": "rank_reached",
            "requirement_value": 3,
            "sort_order": 61
        },
        {
            "id": "rank_b",
            "name": "B-Rank Hunter",
            "description": "Achieve B-Rank",
            "category": "progression",
            "icon": "b.circle.fill",
            "xp_reward": 400,
            "rarity": "epic",
            "requirement_type": "rank_reached",
            "requirement_value": 4,
            "sort_order": 62
        },
        {
            "id": "rank_a",
            "name": "A-Rank Hunter",
            "description": "Achieve A-Rank",
            "category": "progression",
            "icon": "a.circle.fill",
            "xp_reward": 600,
            "rarity": "epic",
            "requirement_type": "rank_reached",
            "requirement_value": 5,
            "sort_order": 63
        },
        {
            "id": "rank_s",
            "name": "S-Rank Hunter",
            "description": "Achieve the legendary S-Rank",
            "category": "progression",
            "icon": "s.circle.fill",
            "xp_reward": 1000,
            "rarity": "legendary",
            "requirement_type": "rank_reached",
            "requirement_value": 6,
            "sort_order": 64
        },

        # Streak achievements
        {
            "id": "streak_7",
            "name": "7-Day Warrior",
            "description": "Maintain a 7-day workout streak",
            "category": "consistency",
            "icon": "flame.fill",
            "xp_reward": 150,
            "rarity": "rare",
            "requirement_type": "streak_days",
            "requirement_value": 7,
            "sort_order": 70
        },
        {
            "id": "streak_14",
            "name": "Fortnight Fighter",
            "description": "Maintain a 14-day workout streak",
            "category": "consistency",
            "icon": "flame.circle.fill",
            "xp_reward": 300,
            "rarity": "epic",
            "requirement_type": "streak_days",
            "requirement_value": 14,
            "sort_order": 71
        },
        {
            "id": "streak_30",
            "name": "30-Day Legend",
            "description": "Maintain a 30-day workout streak",
            "category": "consistency",
            "icon": "star.fill",
            "xp_reward": 500,
            "rarity": "legendary",
            "requirement_type": "streak_days",
            "requirement_value": 30,
            "sort_order": 72
        },
    ]

    for ach_data in achievements:
        existing = db.query(AchievementDefinition).filter(
            AchievementDefinition.id == ach_data["id"]
        ).first()

        if not existing:
            achievement = AchievementDefinition(**ach_data)
            db.add(achievement)

    db.commit()
