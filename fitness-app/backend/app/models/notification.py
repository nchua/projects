"""
Device token and notification preference models for push notifications
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, UniqueConstraint

from app.core.database import Base


class NotificationType(str, enum.Enum):
    """All notification types — split into server-sent (APNs) and local (on-device)"""
    # Server-sent (APNs)
    FRIEND_REQUEST_RECEIVED = "friend_request_received"
    FRIEND_REQUEST_ACCEPTED = "friend_request_accepted"
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"
    LEVEL_UP = "level_up"
    RANK_PROMOTION = "rank_promotion"
    WEEKLY_REPORT_READY = "weekly_report_ready"
    # Local (on-device)
    STREAK_AT_RISK = "streak_at_risk"


# Convenience sets for categorization
SERVER_SENT_TYPES = {
    NotificationType.FRIEND_REQUEST_RECEIVED,
    NotificationType.FRIEND_REQUEST_ACCEPTED,
    NotificationType.ACHIEVEMENT_UNLOCKED,
    NotificationType.LEVEL_UP,
    NotificationType.RANK_PROMOTION,
    NotificationType.WEEKLY_REPORT_READY,
}

LOCAL_TYPES = {
    NotificationType.STREAK_AT_RISK,
}


class DeviceToken(Base):
    """Registered device tokens for push notifications"""
    __tablename__ = "device_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, nullable=False)
    platform = Column(String, nullable=False, default="ios")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint('token', name='uq_device_token'),
        Index('ix_device_tokens_user_id', 'user_id'),
        Index('ix_device_tokens_token', 'token'),
    )


class NotificationPreference(Base):
    """Per-user notification type preferences"""
    __tablename__ = "notification_preferences"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notification_type = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'notification_type', name='uq_user_notification_type'),
        Index('ix_notification_preferences_user_id', 'user_id'),
    )
