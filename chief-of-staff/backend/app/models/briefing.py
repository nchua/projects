"""Briefing model."""

import uuid

from sqlalchemy import Column, String, Date, DateTime, ForeignKey, UniqueConstraint
from app.core.types import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Briefing(Base):
    """A daily briefing (morning) generated for the user."""

    __tablename__ = "briefings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    briefing_type = Column(String, nullable=False, default="morning")  # BriefingType
    date = Column(Date, nullable=False)

    # Structured content (calendar_events, overdue_tasks, todays_tasks, action_items,
    # integration_health, ai_insights)
    content = Column(JSONB, nullable=True)

    # Which integrations were unavailable
    integration_gaps = Column(JSONB, nullable=True)

    generated_at = Column(DateTime(timezone=True), nullable=True)
    viewed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="briefings")

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_briefing_user_date"),
    )
