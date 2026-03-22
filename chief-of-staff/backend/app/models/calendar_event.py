"""CalendarEvent model for cached calendar events."""

import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from app.core.types import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CalendarEvent(Base):
    """A cached calendar event from Google or Apple Calendar."""

    __tablename__ = "calendar_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    provider = Column(String, nullable=False)  # CalendarProvider enum
    external_id = Column(String, nullable=False)
    calendar_id = Column(String, nullable=True)

    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    location = Column(String, nullable=True)
    is_all_day = Column(Boolean, nullable=False, default=False)

    attendees = Column(JSONB, nullable=True)

    needs_prep = Column(Boolean, nullable=False, default=False)
    prep_notes = Column(Text, nullable=True)

    synced_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="calendar_events")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "external_id",
            name="uq_calendar_event_user_provider_external_id",
        ),
    )
