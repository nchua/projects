"""Trip model."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.enums import TravelMode, TripStatus


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        Index(
            "ix_trips_user_status_arrival",
            "user_id",
            "status",
            "arrival_time",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Origin
    origin_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    origin_address: Mapped[str] = mapped_column(
        String(500), nullable=False, default=""
    )
    origin_lat: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    origin_lng: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    origin_is_current_location: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Destination
    dest_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    dest_address: Mapped[str] = mapped_column(String(500), nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lng: Mapped[float] = mapped_column(Float, nullable=False)

    # Timing
    arrival_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    travel_mode: Mapped[TravelMode] = mapped_column(
        Enum(TravelMode, name="travelmode", create_constraint=True),
        nullable=False,
        default=TravelMode.driving,
    )
    buffer_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15
    )

    # Monitoring state
    status: Mapped[TripStatus] = mapped_column(
        Enum(TripStatus, name="tripstatus", create_constraint=True),
        nullable=False,
        default=TripStatus.pending,
        index=True,
    )
    monitoring_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_eta_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notify_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    notified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    notification_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    baseline_duration_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Recurrence
    is_recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    recurrence_rule: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # Calendar integration
    calendar_event_id: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
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
    user = relationship("User", back_populates="trips")
    origin_location = relationship(
        "SavedLocation", foreign_keys=[origin_location_id]
    )
    dest_location = relationship(
        "SavedLocation", foreign_keys=[dest_location_id]
    )
    eta_snapshots = relationship(
        "TripEtaSnapshot",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "NotificationLog",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
