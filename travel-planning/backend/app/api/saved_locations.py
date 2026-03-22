"""Saved location CRUD endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.saved_location import SavedLocation
from app.models.user import User
from app.schemas.saved_location import (
    CreateSavedLocationRequest,
    SavedLocationResponse,
    UpdateSavedLocationRequest,
)

router = APIRouter(prefix="/locations", tags=["locations"])

MAX_SAVED_LOCATIONS = 10


async def _get_user_location(
    db: AsyncSession,
    location_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SavedLocation:
    """Fetch a saved location owned by the user, or raise 404."""
    result = await db.execute(
        select(SavedLocation).where(
            SavedLocation.id == location_id,
            SavedLocation.user_id == user_id,
        )
    )
    location = result.scalar_one_or_none()
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved location not found",
            headers={"X-Error-Code": "LOCATION_NOT_FOUND"},
        )
    return location


@router.post(
    "",
    response_model=SavedLocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_location(
    body: CreateSavedLocationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedLocationResponse:
    """Create a saved location with limit and uniqueness checks."""
    # Check max locations limit
    count_result = await db.execute(
        select(func.count()).where(
            SavedLocation.user_id == current_user.id
        )
    )
    count = count_result.scalar_one()
    if count >= MAX_SAVED_LOCATIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 10 saved locations reached",
            headers={"X-Error-Code": "LOCATION_LIMIT_REACHED"},
        )

    # Check name uniqueness for this user
    name_result = await db.execute(
        select(SavedLocation).where(
            SavedLocation.user_id == current_user.id,
            SavedLocation.name == body.name,
        )
    )
    if name_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A location named '{body.name}' already exists",
            headers={"X-Error-Code": "LOCATION_NAME_DUPLICATE"},
        )

    location = SavedLocation(
        user_id=current_user.id,
        name=body.name,
        address=body.address,
        latitude=body.latitude,
        longitude=body.longitude,
        icon=body.icon,
        sort_order=body.sort_order,
    )
    db.add(location)
    await db.flush()
    await db.refresh(location)

    return SavedLocationResponse.model_validate(location)


@router.get("", response_model=list[SavedLocationResponse])
async def list_locations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SavedLocationResponse]:
    """List all saved locations for the current user."""
    result = await db.execute(
        select(SavedLocation)
        .where(SavedLocation.user_id == current_user.id)
        .order_by(SavedLocation.sort_order.asc(), SavedLocation.created_at.asc())
    )
    locations = result.scalars().all()
    return [SavedLocationResponse.model_validate(loc) for loc in locations]


@router.get("/{location_id}", response_model=SavedLocationResponse)
async def get_location(
    location_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedLocationResponse:
    """Get a single saved location."""
    location = await _get_user_location(db, location_id, current_user.id)
    return SavedLocationResponse.model_validate(location)


@router.put("/{location_id}", response_model=SavedLocationResponse)
async def update_location(
    location_id: uuid.UUID,
    body: UpdateSavedLocationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedLocationResponse:
    """Update a saved location with name uniqueness validation."""
    location = await _get_user_location(db, location_id, current_user.id)

    update_data = body.model_dump(exclude_unset=True)

    # Check name uniqueness if name is being changed
    if "name" in update_data and update_data["name"] != location.name:
        name_result = await db.execute(
            select(SavedLocation).where(
                SavedLocation.user_id == current_user.id,
                SavedLocation.name == update_data["name"],
                SavedLocation.id != location_id,
            )
        )
        if name_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A location named '{update_data['name']}' already exists",
                headers={"X-Error-Code": "LOCATION_NAME_DUPLICATE"},
            )

    for field, value in update_data.items():
        setattr(location, field, value)

    await db.flush()
    await db.refresh(location)

    return SavedLocationResponse.model_validate(location)


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a saved location.

    Trips referencing it will have their location FK set to NULL
    (ON DELETE SET NULL), but denormalized address/lat/lng are preserved.
    """
    location = await _get_user_location(db, location_id, current_user.id)
    await db.delete(location)
    await db.flush()
