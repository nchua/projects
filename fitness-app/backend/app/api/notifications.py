"""
Notification API endpoints — device token registration and preference management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.notification import DeviceToken, NotificationPreference, NotificationType
from app.schemas.notification import (
    DeviceTokenRegister,
    DeviceTokenResponse,
    NotificationPreferenceBulkUpdate,
    NotificationPreferencesListResponse,
    NotificationPreferenceItem,
)

router = APIRouter()


@router.post("/device-token", response_model=DeviceTokenResponse)
async def register_device_token(
    payload: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register or reactivate a device token for push notifications."""
    existing = db.query(DeviceToken).filter(
        DeviceToken.token == payload.token
    ).first()

    if existing:
        # Reactivate and reassign to current user
        existing.user_id = current_user.id
        existing.platform = payload.platform
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
    else:
        new_token = DeviceToken(
            user_id=current_user.id,
            token=payload.token,
            platform=payload.platform,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(new_token)

    db.commit()
    return DeviceTokenResponse(message="Device token registered")


@router.delete("/device-token", response_model=DeviceTokenResponse)
async def deactivate_device_token(
    payload: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a device token (e.g., on logout)."""
    token_record = db.query(DeviceToken).filter(
        DeviceToken.token == payload.token,
        DeviceToken.user_id == current_user.id,
    ).first()

    if token_record:
        token_record.is_active = False
        token_record.updated_at = datetime.utcnow()
        db.commit()

    return DeviceTokenResponse(message="Device token deactivated")


@router.get("/preferences", response_model=NotificationPreferencesListResponse)
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all notification preferences. Missing types default to enabled."""
    existing = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == current_user.id,
    ).all()

    prefs_map = {p.notification_type: p.enabled for p in existing}

    # Return all types, defaulting to enabled
    items = []
    for nt in NotificationType:
        items.append(NotificationPreferenceItem(
            notification_type=nt.value,
            enabled=prefs_map.get(nt.value, True),
        ))

    return NotificationPreferencesListResponse(preferences=items)


@router.put("/preferences", response_model=NotificationPreferencesListResponse)
async def update_notification_preferences(
    payload: NotificationPreferenceBulkUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk update notification preferences."""
    # Validate notification types
    valid_types = {nt.value for nt in NotificationType}
    for pref in payload.preferences:
        if pref.notification_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification type: {pref.notification_type}",
            )

    now = datetime.utcnow()
    for pref in payload.preferences:
        existing = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == current_user.id,
            NotificationPreference.notification_type == pref.notification_type,
        ).first()

        if existing:
            existing.enabled = pref.enabled
            existing.updated_at = now
        else:
            new_pref = NotificationPreference(
                user_id=current_user.id,
                notification_type=pref.notification_type,
                enabled=pref.enabled,
                created_at=now,
                updated_at=now,
            )
            db.add(new_pref)

    db.commit()

    # Return updated full list
    return await get_notification_preferences(current_user=current_user, db=db)
