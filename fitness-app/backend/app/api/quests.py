"""
Quest API endpoints - Daily quests and rewards
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.quest_service import (
    get_daily_quests,
    claim_quest_reward,
    seed_quest_definitions,
    generate_daily_quests
)
from app.schemas.quest import (
    DailyQuestsResponse,
    QuestResponse,
    QuestClaimResponse
)

router = APIRouter()


@router.get("", response_model=DailyQuestsResponse)
@router.get("/", response_model=DailyQuestsResponse)
async def get_quests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get today's daily quests for the current user.

    If no quests have been assigned today, new quests will be generated.

    Returns:
        DailyQuestsResponse with quests list and refresh timestamp
    """
    result = get_daily_quests(db, current_user.id)

    return DailyQuestsResponse(
        quests=[QuestResponse(**q) for q in result["quests"]],
        refresh_at=result["refresh_at"],
        completed_count=result["completed_count"],
        total_count=result["total_count"]
    )


@router.post("/{quest_id}/claim", response_model=QuestClaimResponse)
async def claim_quest(
    quest_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Claim XP reward for a completed quest.

    Args:
        quest_id: The UserQuest ID to claim

    Returns:
        QuestClaimResponse with XP earned and progression info

    Raises:
        400: Quest not found, not completed, or already claimed
    """
    try:
        result = claim_quest_reward(db, current_user.id, quest_id)
        db.commit()
        return QuestClaimResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/refresh")
async def refresh_quests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Force refresh daily quests (admin/testing endpoint).

    This will generate new quests even if quests already exist for today.
    Use with caution in production.

    Returns:
        New quests for today
    """
    # Delete today's existing quests
    from app.models.quest import UserQuest
    from app.services.quest_service import get_today_utc

    today = get_today_utc()
    db.query(UserQuest).filter(
        UserQuest.user_id == current_user.id,
        UserQuest.assigned_date == today
    ).delete()

    # Generate new ones
    user_quests = generate_daily_quests(db, current_user.id)
    db.commit()

    # Return the new quests
    result = get_daily_quests(db, current_user.id)
    return DailyQuestsResponse(
        quests=[QuestResponse(**q) for q in result["quests"]],
        refresh_at=result["refresh_at"],
        completed_count=result["completed_count"],
        total_count=result["total_count"]
    )


@router.post("/seed")
async def seed_quests(db: Session = Depends(get_db)):
    """
    Seed quest definitions (admin endpoint).

    This populates the quest_definitions table with all
    available quest templates. Safe to call multiple times.

    Returns:
        Number of quests created
    """
    count = seed_quest_definitions(db)
    return {
        "message": "Quest definitions seeded successfully",
        "quests_created": count
    }
