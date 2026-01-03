"""
Progress API endpoints - XP, leveling, and achievements
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.pr import PR
from app.services.xp_service import (
    get_user_progress_summary,
    get_or_create_user_progress,
    xp_to_next_level,
    level_progress
)
from app.services.achievement_service import (
    get_user_achievements,
    get_recently_unlocked,
    check_and_unlock_achievements,
    seed_achievement_definitions
)
from app.schemas.progress import (
    UserProgressResponse,
    AchievementResponse,
    AchievementsListResponse,
    RecentAchievementsResponse
)

router = APIRouter()


@router.get("", response_model=UserProgressResponse)
@router.get("/", response_model=UserProgressResponse)
async def get_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's current XP, level, and rank progress

    Returns:
        UserProgressResponse with current stats
    """
    summary = get_user_progress_summary(db, current_user.id)
    return UserProgressResponse(**summary)


@router.get("/achievements", response_model=AchievementsListResponse)
async def get_achievements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all achievements with unlock status for current user

    Returns:
        List of all achievements showing which are unlocked
    """
    achievements = get_user_achievements(db, current_user.id)
    unlocked_count = sum(1 for a in achievements if a["unlocked"])

    return AchievementsListResponse(
        achievements=[AchievementResponse(**a) for a in achievements],
        total_unlocked=unlocked_count,
        total_available=len(achievements)
    )


@router.get("/achievements/recent", response_model=RecentAchievementsResponse)
async def get_recent_achievements(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get recently unlocked achievements

    Args:
        limit: Max number of achievements to return (default 5)

    Returns:
        List of recently unlocked achievements
    """
    achievements = get_recently_unlocked(db, current_user.id, limit)
    return RecentAchievementsResponse(
        achievements=[AchievementResponse(**a, unlocked=True) for a in achievements]
    )


@router.post("/check-achievements")
async def check_achievements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger achievement check for current user

    This is useful for retroactively checking achievements
    after data migration or bug fixes.

    Returns:
        List of newly unlocked achievements
    """
    progress = get_or_create_user_progress(db, current_user.id)

    # Build context for achievement checking
    # Get exercise PRs for strength achievements
    prs = db.query(PR).filter(PR.user_id == current_user.id).all()
    exercise_prs = {}
    for pr in prs:
        exercise_name = pr.exercise.name.lower() if pr.exercise else ""
        if exercise_name not in exercise_prs or pr.weight > exercise_prs[exercise_name]:
            exercise_prs[exercise_name] = pr.weight

    context = {
        "workout_count": progress.total_workouts,
        "level": progress.level,
        "rank": progress.rank,
        "prs_count": progress.total_prs,
        "current_streak": progress.current_streak,
        "exercise_prs": exercise_prs
    }

    newly_unlocked = check_and_unlock_achievements(db, current_user.id, context)
    db.commit()

    return {
        "achievements_unlocked": newly_unlocked,
        "count": len(newly_unlocked)
    }


@router.post("/seed-achievements")
async def seed_achievements(db: Session = Depends(get_db)):
    """
    Seed achievement definitions (admin endpoint)

    This populates the achievement_definitions table with all
    available achievements. Safe to call multiple times.
    """
    seed_achievement_definitions(db)
    return {"message": "Achievement definitions seeded successfully"}
