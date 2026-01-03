"""
Exercise model for library and custom exercises
"""
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class Exercise(Base):
    """Exercise library entry (seeded + custom)"""
    __tablename__ = "exercises"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    canonical_id = Column(String, nullable=True, index=True)  # For aliases (e.g., "squat")

    # Categorization
    category = Column(String, nullable=True)  # Push, Pull, Legs, Core, Accessories
    primary_muscle = Column(String, nullable=True)
    secondary_muscles = Column(JSON, nullable=True)  # List of secondary muscles

    # Custom exercise tracking
    is_custom = Column(Boolean, default=False, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # NULL for seeded exercises

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="custom_exercises")
    workout_exercises = relationship("WorkoutExercise", back_populates="exercise", cascade="all, delete-orphan")
    prs = relationship("PR", back_populates="exercise", cascade="all, delete-orphan")
