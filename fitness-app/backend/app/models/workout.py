"""
Workout session, exercises, and sets models
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.core.database import Base


class WeightUnit(str, enum.Enum):
    """Weight units for sets"""
    LB = "lb"
    KG = "kg"


class WorkoutSession(Base):
    """Workout session metadata"""
    __tablename__ = "workout_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Client-generated idempotency key. The iOS offline queue stamps a UUID on
    # every WorkoutCreate so a retry after a network blip that actually
    # succeeded server-side returns the existing row instead of creating a
    # duplicate. Nullable for legacy rows and the web path that doesn't send
    # one. Uniqueness is enforced at (user_id, client_id) via the index below.
    client_id = Column(String, nullable=True, index=True)

    date = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=True)
    session_rpe = Column(Integer, nullable=True)  # Optional 1-10 rating for entire session
    notes = Column(Text, nullable=True)

    # Sync tracking
    synced_at = Column(DateTime, nullable=True)

    # Soft delete
    deleted_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="workout_sessions")
    workout_exercises = relationship("WorkoutExercise", back_populates="session", cascade="all, delete-orphan", order_by="WorkoutExercise.order_index")

    # Enforce per-user client_id uniqueness so a retry returns the existing
    # session. Postgres treats multiple NULLs as distinct, so legacy rows and
    # web clients that don't send a client_id aren't affected.
    #
    # `postgresql_where` must be a SQL clause, not a detached Column(). Using
    # Column("client_id") here creates a brand-new Column object that isn't
    # tied to this table, so SQLAlchemy emits invalid DDL for the partial
    # index (the migration itself uses sa.text, so Postgres deploys are fine,
    # but Base.metadata.create_all under tests would fail). Keep the raw
    # SQL text to match the migration.
    __table_args__ = (
        Index(
            "ix_workout_sessions_user_client_unique",
            "user_id",
            "client_id",
            unique=True,
            postgresql_where=text("client_id IS NOT NULL"),
        ),
    )


class WorkoutExercise(Base):
    """Exercise within a workout session"""
    __tablename__ = "workout_exercises"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("workout_sessions.id"), nullable=False, index=True)
    exercise_id = Column(String, ForeignKey("exercises.id"), nullable=False, index=True)

    order_index = Column(Integer, nullable=False)  # Order of exercises in the workout
    superset_group_id = Column(String, nullable=True, index=True)  # Groups exercises performed as superset

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    session = relationship("WorkoutSession", back_populates="workout_exercises")
    exercise = relationship("Exercise", back_populates="workout_exercises")
    sets = relationship("Set", back_populates="workout_exercise", cascade="all, delete-orphan", order_by="Set.set_number")


class Set(Base):
    """Individual set within an exercise"""
    __tablename__ = "sets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workout_exercise_id = Column(String, ForeignKey("workout_exercises.id"), nullable=False, index=True)

    weight = Column(Float, nullable=False)
    weight_unit = Column(Enum(WeightUnit), default=WeightUnit.LB, nullable=False)
    reps = Column(Integer, nullable=False)

    rpe = Column(Integer, nullable=True)  # Rate of Perceived Exertion 1-10
    rir = Column(Integer, nullable=True)  # Reps in Reserve 0-5

    set_number = Column(Integer, nullable=False)  # Order within the exercise
    e1rm = Column(Float, nullable=True)  # Computed estimated 1RM

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    workout_exercise = relationship("WorkoutExercise", back_populates="sets")
