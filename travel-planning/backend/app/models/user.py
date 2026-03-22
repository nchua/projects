"""User model."""

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.enums import AuthProvider, TravelMode


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    display_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="authprovider", create_constraint=True),
        nullable=False,
        default=AuthProvider.email,
    )
    apple_user_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    default_buffer_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15
    )
    default_travel_mode: Mapped[TravelMode] = mapped_column(
        Enum(TravelMode, name="travelmode", create_constraint=True),
        nullable=False,
        default=TravelMode.driving,
    )
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="America/Los_Angeles"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    trips = relationship("Trip", back_populates="user", lazy="selectin")
    saved_locations = relationship(
        "SavedLocation", back_populates="user", lazy="selectin"
    )
    device_tokens = relationship(
        "DeviceToken", back_populates="user", lazy="selectin"
    )
    notification_logs = relationship(
        "NotificationLog", back_populates="user", cascade="all, delete-orphan"
    )
