"""User profile and preferences endpoints."""

from datetime import time

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.user import UpdateUserRequest, UserResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the current user's profile and preferences."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update current user's profile and preferences.

    Only provided (non-None) fields are updated.
    """
    update_data = body.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field in ("quiet_hours_start", "quiet_hours_end") and value is not None:
            # Convert "HH:MM" string to time object for DB storage
            parts = value.split(":")
            value = time(int(parts[0]), int(parts[1]))
        setattr(current_user, field, value)

    await db.flush()
    await db.refresh(current_user)

    return UserResponse.model_validate(current_user)
