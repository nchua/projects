"""RecurringTask and TaskCompletion models."""

import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Date,
    Integer,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RecurringTask(Base):
    """A recurring task (daily non-negotiable, weekly, monthly, or custom)."""

    __tablename__ = "recurring_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Cadence stored as String, validated by Cadence enum in schemas
    cadence = Column(String, nullable=False)
    cron_expression = Column(String, nullable=True)  # For custom cadence

    # Time window
    start_time = Column(String, nullable=True)  # e.g. "09:00"
    end_time = Column(String, nullable=True)    # e.g. "17:00"
    timezone = Column(String, nullable=True)    # Defaults to user timezone

    # Behavior
    missed_behavior = Column(String, nullable=False, default="roll_forward")
    priority = Column(String, nullable=False, default="non_negotiable")

    # Tracking
    streak_count = Column(Integer, nullable=False, default=0)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Ordering and archival
    sort_order = Column(Integer, nullable=False, default=0)
    is_archived = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="recurring_tasks")
    completions = relationship(
        "TaskCompletion", back_populates="recurring_task", cascade="all, delete-orphan"
    )


class TaskCompletion(Base):
    """A single completion record for a recurring task on a specific date."""

    __tablename__ = "task_completions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recurring_task_id = Column(
        String, ForeignKey("recurring_tasks.id"), nullable=False, index=True
    )
    date = Column(Date, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    skipped = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    recurring_task = relationship("RecurringTask", back_populates="completions")

    __table_args__ = (
        UniqueConstraint("recurring_task_id", "date", name="uq_task_completion_task_date"),
    )
