"""
User API endpoints for username management and user search
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.progress import UserProgress
from app.schemas.user import UsernameUpdate, UsernameCheckResponse, UserPublicResponse
from app.services.xp_service import get_or_create_user_progress

router = APIRouter()


@router.get("/username/check", response_model=UsernameCheckResponse)
async def check_username_availability(
    username: str = Query(..., min_length=3, max_length=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if a username is available

    Args:
        username: The username to check (3-20 characters)

    Returns:
        UsernameCheckResponse with availability status
    """
    # Normalize to lowercase
    username_lower = username.lower()

    # Check if username exists (excluding current user)
    existing = db.query(User).filter(
        User.username == username_lower,
        User.id != current_user.id
    ).first()

    return UsernameCheckResponse(
        username=username_lower,
        available=existing is None
    )


@router.put("/username")
async def set_username(
    data: UsernameUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Set or update the current user's username

    Args:
        data: UsernameUpdate with the new username

    Returns:
        Success message with the new username

    Raises:
        HTTPException 409: If username is already taken
    """
    username = data.username  # Already validated and lowercased by Pydantic

    # Check if username is taken by another user
    existing = db.query(User).filter(
        User.username == username,
        User.id != current_user.id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken"
        )

    # Update username
    current_user.username = username
    db.commit()

    return {
        "message": "Username updated successfully",
        "username": username
    }


@router.get("/search", response_model=List[UserPublicResponse])
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Search for users by username

    Args:
        q: Search query (matches usernames containing this string)
        limit: Maximum number of results (default 20)

    Returns:
        List of UserPublicResponse with matching users
    """
    # Normalize query
    query = q.lower()

    # Search users by username (exclude current user)
    users = db.query(User).filter(
        User.username.isnot(None),
        User.username.ilike(f"%{query}%"),
        User.id != current_user.id
    ).limit(limit).all()

    # Get progress info for each user
    results = []
    for user in users:
        progress = get_or_create_user_progress(db, user.id)
        results.append(UserPublicResponse(
            id=user.id,
            username=user.username,
            rank=progress.rank,
            level=progress.level
        ))

    return results
