"""
Goal models - strength PR goals and progress snapshots
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class GoalStatus(str, enum.Enum):
    """Status of a user's strength goal"""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


class Goal(Base):
    """User's strength PR goal"""
    __tablename__ = "goals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    exercise_id = Column(String, ForeignKey("exercises.id"), nullable=False)

    # Target
    target_weight = Column(Float, nullable=False)  # Target weight to lift
    target_reps = Column(Integer, default=1, nullable=False)  # Target reps (1 = true 1RM)
    weight_unit = Column(String, default="lb", nullable=False)  # lb or kg
    deadline = Column(Date, nullable=False)

    # Progress tracking
    starting_e1rm = Column(Float, nullable=True)  # e1RM when goal was created
    current_e1rm = Column(Float, nullable=True)  # Latest e1RM for this exercise

    # Status
    status = Column(String, default="active", nullable=False)  # GoalStatus
    achieved_at = Column(DateTime, nullable=True)
    abandoned_at = Column(DateTime, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="goals")
    exercise = relationship("Exercise")
    # Progress snapshots for tracking e1RM over time
    progress_snapshots = relationship("GoalProgressSnapshot", back_populates="goal", cascade="all, delete-orphan", order_by="GoalProgressSnapshot.recorded_at")


class GoalProgressSnapshot(Base):
    """Historical e1RM snapshot for tracking goal progress over time"""
    __tablename__ = "goal_progress_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    goal_id = Column(String, ForeignKey("goals.id"), nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False)  # When this e1RM was achieved
    e1rm = Column(Float, nullable=False)  # Estimated 1RM at this point

    # Optional: actual lift details that produced this e1RM
    weight = Column(Float, nullable=True)  # Weight lifted
    reps = Column(Integer, nullable=True)  # Reps performed
    workout_id = Column(String, ForeignKey("workout_sessions.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    goal = relationship("Goal", back_populates="progress_snapshots")
    workout = relationship("WorkoutSession")
