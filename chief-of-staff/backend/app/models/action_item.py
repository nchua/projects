"""ActionItem model for AI-extracted and manual action items."""

import uuid

from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ActionItem(Base):
    """An action item extracted by AI or added manually."""

    __tablename__ = "action_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    source = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    source_url = Column(String, nullable=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    extracted_deadline = Column(DateTime(timezone=True), nullable=True)
    confidence_score = Column(Float, nullable=True)

    priority = Column(String, nullable=False, default="medium")
    status = Column(String, nullable=False, default="new")
    dismiss_reason = Column(String, nullable=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)

    linked_task_id = Column(
        String, ForeignKey("recurring_tasks.id"), nullable=True
    )

    dedup_hash = Column(String, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    actioned_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="action_items")
    linked_task = relationship("RecurringTask")
    contact_links = relationship(
        "ActionItemContact", back_populates="action_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_action_item_dedup_hash"),
    )
