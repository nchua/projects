"""Device token registration endpoints for push notifications."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.device_token import DeviceToken
from app.models.user import User
from app.schemas.device_token import (
    DeviceTokenResponse,
    RegisterDeviceTokenRequest,
    UnregisterDeviceTokenRequest,
)

router = APIRouter(prefix="/device-tokens", tags=["device-tokens"])


@router.post(
    "", response_model=DeviceTokenResponse, status_code=status.HTTP_201_CREATED
)
async def register_device_token(
    body: RegisterDeviceTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceTokenResponse:
    """Register or upsert an FCM device token.

    If the token already exists for this user, reactivates it.
    If it exists for a different user, reassigns it to the current user.
    """
    # Check if token already exists
    result = await db.execute(
        select(DeviceToken).where(DeviceToken.token == body.token)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Reassign to current user if needed, and reactivate
        existing.user_id = current_user.id
        existing.platform = body.platform
        existing.is_active = True
        await db.flush()
        await db.refresh(existing)
        return DeviceTokenResponse.model_validate(existing)

    # Create new token
    device_token = DeviceToken(
        user_id=current_user.id,
        token=body.token,
        platform=body.platform,
        is_active=True,
    )
    db.add(device_token)
    await db.flush()
    await db.refresh(device_token)

    return DeviceTokenResponse.model_validate(device_token)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device_token(
    body: UnregisterDeviceTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deactivate a device token (set is_active to False)."""
    result = await db.execute(
        select(DeviceToken).where(
            DeviceToken.token == body.token,
            DeviceToken.user_id == current_user.id,
        )
    )
    device_token = result.scalar_one_or_none()

    if device_token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device token not found",
            headers={"X-Error-Code": "TOKEN_NOT_FOUND"},
        )

    device_token.is_active = False
    await db.flush()
