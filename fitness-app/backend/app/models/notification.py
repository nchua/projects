"""
Device token and notification preference models for push notifications
"""
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, UniqueConstraint, Index
from datetime import datetime
import uuid
import enum
from app.core.database import Base


class NotificationType(str, enum.Enum):
    """All notification types — split into server-sent (APNs) and local (on-device)"""
    # Server-sent (APNs)
    FRIEND_REQUEST_RECEIVED = "friend_request_received"
    FRIEND_REQUEST_ACCEPTED = "friend_request_accepted"
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"
    LEVEL_UP = "level_up"
    RANK_PROMOTION = "rank_promotion"
    DUNGEON_SPAWNED = "dungeon_spawned"
    WEEKLY_REPORT_READY = "weekly_report_ready"
    MISSION_OFFERED = "mission_offered"
    # Local (on-device)
    QUEST_COMPLETED = "quest_completed"
    STREAK_AT_RISK = "streak_at_risk"
    QUEST_RESET = "quest_reset"
    DUNGEON_EXPIRING = "dungeon_expiring"
    MISSION_EXPIRING = "mission_expiring"


# Convenience sets for categorization
SERVER_SENT_TYPES = {
    NotificationType.FRIEND_REQUEST_RECEIVED,
    NotificationType.FRIEND_REQUEST_ACCEPTED,
    NotificationType.ACHIEVEMENT_UNLOCKED,
    NotificationType.LEVEL_UP,
    NotificationType.RANK_PROMOTION,
    NotificationType.DUNGEON_SPAWNED,
    NotificationType.WEEKLY_REPORT_READY,
    NotificationType.MISSION_OFFERED,
}

LOCAL_TYPES = {
    NotificationType.QUEST_COMPLETED,
    NotificationType.STREAK_AT_RISK,
    NotificationType.QUEST_RESET,
    NotificationType.DUNGEON_EXPIRING,
    NotificationType.MISSION_EXPIRING,
}


class DeviceToken(Base):
    """Registered device tokens for push notifications"""
    __tablename__ = "device_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, nullable=False)
    platform = Column(String, nullable=False, default="ios")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'notification_type', name='uq_user_notification_type'),
        Index('ix_notification_preferences_user_id', 'user_id'),
    )
