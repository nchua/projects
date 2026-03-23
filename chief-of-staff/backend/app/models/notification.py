"""DeviceToken and NotificationLog models."""

import uuid

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DeviceToken(Base):
    """A registered Web Push subscription for browser notifications."""

    __tablename__ = "device_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    token = Column(Text, nullable=False)  # Web Push subscription JSON
    platform = Column(String, nullable=True, default="web")

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="device_tokens")

    __table_args__ = (
        UniqueConstraint("user_id", "token", name="uq_device_token_user_token"),
    )


class NotificationLog(Base):
    """Log of notifications sent to users."""

    __tablename__ = "notification_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    notification_type = Column(String, nullable=False)  # NotificationType enum
    channel = Column(String, nullable=False)  # NotificationChannel enum

    related_entity_type = Column(String, nullable=True)
    related_entity_id = Column(String, nullable=True)

    title = Column(String, nullable=True)
    body = Column(Text, nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="notification_logs")
