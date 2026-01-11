"""
Dungeon API endpoints - Gate system for multi-day challenges
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.dungeon_service import (
    get_user_dungeons,
    get_dungeon_detail,
    accept_dungeon,
    abandon_dungeon,
    claim_dungeon_rewards,
    get_dungeon_history,
    maybe_spawn_dungeon
)
from app.schemas.dungeon import (
    DungeonsResponse,
    DungeonResponse,
    DungeonSummaryResponse,
    DungeonAcceptResponse,
    DungeonAbandonResponse,
    DungeonClaimResponse,
    DungeonHistoryResponse,
    DungeonSpawnResponse
)

router = APIRouter()


@router.get("", response_model=DungeonsResponse)
@router.get("/", response_model=DungeonsResponse)
async def get_dungeons(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's dungeons (mission board).

    Returns available, active, and completed (unclaimed) dungeons.
    Expired dungeons are automatically marked as such.
    """
    result = get_user_dungeons(db, current_user.id)
    db.commit()

    return DungeonsResponse(
        available=[DungeonSummaryResponse(**d) for d in result["available"]],
        active=[DungeonSummaryResponse(**d) for d in result["active"]],
        completed_unclaimed=[DungeonSummaryResponse(**d) for d in result["completed_unclaimed"]],
        user_level=result["user_level"],
        user_rank=result["user_rank"]
    )


@router.get("/history", response_model=DungeonHistoryResponse)
async def get_dungeons_history(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get past dungeon attempts (claimed, expired, abandoned).
    """
    result = get_dungeon_history(db, current_user.id, skip, limit)

    return DungeonHistoryResponse(
        dungeons=[DungeonSummaryResponse(**d) for d in result["dungeons"]],
        total_completed=result["total_completed"],
        total_abandoned=result["total_abandoned"],
        total_expired=result["total_expired"]
    )


@router.get("/{dungeon_id}", response_model=DungeonResponse)
async def get_dungeon(
    dungeon_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed dungeon info with all objectives.

    Args:
        dungeon_id: The UserDungeon ID
    """
    result = get_dungeon_detail(db, current_user.id, dungeon_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dungeon not found"
        )

    return DungeonResponse(**result)


@router.post("/{dungeon_id}/accept", response_model=DungeonAcceptResponse)
async def accept_dungeon_endpoint(
    dungeon_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept and enter a dungeon.

    Once accepted, you must complete or abandon the dungeon.
    You can only have one active dungeon at a time.

    Args:
        dungeon_id: The UserDungeon ID to accept
    """
    try:
        result = accept_dungeon(db, current_user.id, dungeon_id)
        db.commit()
        return DungeonAcceptResponse(
            success=result["success"],
            dungeon=DungeonResponse(**result["dungeon"]),
            message=result["message"]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{dungeon_id}/abandon", response_model=DungeonAbandonResponse)
async def abandon_dungeon_endpoint(
    dungeon_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Abandon an active dungeon.

    No penalty is applied for abandoning a dungeon.
    The dungeon will be removed and cannot be resumed.

    Args:
        dungeon_id: The UserDungeon ID to abandon
    """
    try:
        result = abandon_dungeon(db, current_user.id, dungeon_id)
        db.commit()
        return DungeonAbandonResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{dungeon_id}/claim", response_model=DungeonClaimResponse)
async def claim_dungeon_endpoint(
    dungeon_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Claim XP rewards for a completed dungeon.

    Args:
        dungeon_id: The UserDungeon ID to claim

    Returns:
        XP earned breakdown and level/rank progression
    """
    try:
        result = claim_dungeon_rewards(db, current_user.id, dungeon_id)
        db.commit()
        return DungeonClaimResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/spawn/force", response_model=DungeonSpawnResponse)
async def force_spawn_dungeon(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Force spawn a dungeon (admin/testing endpoint).

    Bypasses the random chance and spawns a dungeon immediately
    if the user is not at max available dungeons.
    """
    result = maybe_spawn_dungeon(db, current_user.id, force=True)
    db.commit()

    if result:
        return DungeonSpawnResponse(
            spawned=result["spawned"],
            dungeon=DungeonSummaryResponse(**result["dungeon"]),
            message=result["message"]
        )
    else:
        return DungeonSpawnResponse(
            spawned=False,
            dungeon=None,
            message="Cannot spawn dungeon - at max available dungeons or no eligible dungeons"
        )


@router.post("/seed")
async def seed_dungeons(db: Session = Depends(get_db)):
    """
    Seed dungeon definitions (admin endpoint).

    This populates the dungeon_definitions table with all
    available dungeon templates. Safe to call multiple times.
    """
    from app.services.dungeon_seed import seed_dungeon_definitions
    count = seed_dungeon_definitions(db)
    return {
        "message": "Dungeon definitions seeded successfully",
        "dungeons_created": count
    }
