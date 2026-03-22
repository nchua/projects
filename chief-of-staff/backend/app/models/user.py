"""User model."""

import uuid

from sqlalchemy import Column, String, Boolean, DateTime, Time
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    """User account."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    timezone = Column(String, nullable=True, default="America/Los_Angeles")
    wake_time = Column(Time, nullable=True)
    sleep_time = Column(Time, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    recurring_tasks = relationship(
        "RecurringTask", back_populates="user", cascade="all, delete-orphan"
    )
    action_items = relationship(
        "ActionItem", back_populates="user", cascade="all, delete-orphan"
    )
    one_off_reminders = relationship(
        "OneOffReminder", back_populates="user", cascade="all, delete-orphan"
    )
    contacts = relationship(
        "Contact", back_populates="user", cascade="all, delete-orphan"
    )
    briefings = relationship(
        "Briefing", back_populates="user", cascade="all, delete-orphan"
    )
    integrations = relationship(
        "Integration", back_populates="user", cascade="all, delete-orphan"
    )
    calendar_events = relationship(
        "CalendarEvent", back_populates="user", cascade="all, delete-orphan"
    )
    device_tokens = relationship(
        "DeviceToken", back_populates="user", cascade="all, delete-orphan"
    )
    notification_logs = relationship(
        "NotificationLog", back_populates="user", cascade="all, delete-orphan"
    )
