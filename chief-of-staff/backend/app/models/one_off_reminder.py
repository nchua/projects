"""OneOffReminder model."""

import uuid

from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from app.core.types import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class OneOffReminder(Base):
    """An ad-hoc reminder (time, location, context, or follow-up trigger)."""

    __tablename__ = "one_off_reminders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Trigger
    trigger_type = Column(String, nullable=False)  # TriggerType enum
    trigger_config = Column(JSONB, nullable=True)

    # Optional link back to AI-extracted action item
    source_action_item_id = Column(
        String, ForeignKey("action_items.id"), nullable=True
    )

    # Status
    status = Column(String, nullable=False, default="pending")  # ReminderStatus

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="one_off_reminders")
    source_action_item = relationship("ActionItem")
