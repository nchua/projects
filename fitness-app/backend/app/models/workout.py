"""
Workout session, exercises, and sets models
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
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

    # HealthKit (Apple Watch) workout UUID — the dedup target for the
    # `POST /workouts/import-healthkit` path. Cardio imports create a session
    # stamped with it; strength imports backfill it onto the matched existing
    # session. Nullable for every non-HealthKit row. Uniqueness is enforced at
    # (user_id, hk_uuid) via the partial index below, mirroring client_id.
    hk_uuid = Column(String, nullable=True, index=True)

    date = Column(DateTime, nullable=False, index=True)

    # The user's local calendar day for this session — "what day it was for
    # the lifter". Authoritative for all day bucketing when set. Nullable:
    # legacy watch-import rows store only a UTC instant and can't recover
    # the local day; readers fall back to the midnight convention on `date`
    # (midnight = local day, non-midnight = UTC; see core/utils).
    local_date = Column(Date, nullable=True, index=True)

    # User-facing hunt name ("Back & Biceps Day", "Tennis"). Nullable — when
    # unset, clients fall back to the server-derived suggested name (see
    # hunt_name_service.suggest_hunt_name) and finally the session date.
    name = Column(String(100), nullable=True)

    duration_minutes = Column(Integer, nullable=True)
    session_rpe = Column(Integer, nullable=True)  # Optional 1-10 rating for entire session
    notes = Column(Text, nullable=True)

    # ── Wearable heart-rate summary (rolled up from heart_rate_samples) ──
    # Populated by the Apple Watch companion app (live, in the create payload)
    # or backfilled from the WHOOP API after the session syncs to WHOOP's
    # cloud. All nullable for legacy rows and workouts logged without a
    # wearable. `hr_zone_seconds` is a JSON map of seconds spent per HR zone,
    # e.g. {"z1": 120, "z2": 540, "z3": 300, "z4": 90, "z5": 0}.
    avg_heart_rate = Column(Integer, nullable=True)
    peak_heart_rate = Column(Integer, nullable=True)
    strain = Column(Float, nullable=True)          # WHOOP strain 0-21
    kilojoules = Column(Float, nullable=True)       # Energy expenditure
    hr_zone_seconds = Column(JSON, nullable=True)
    hr_source = Column(String, nullable=True)       # "apple_watch" | "whoop" | "screenshot"

    # ── Cardio metadata (HealthKit imports and future cardio logging) ──
    # activity_type is the controlled vocab from the HealthKit import (e.g.
    # "Outdoor Run"); distance covers runs/rides/swims. duration_seconds
    # keeps the exact workout length (duration_minutes is rounded, which is
    # too coarse for pace math). All nullable — strength sessions and legacy
    # rows leave them unset.
    activity_type = Column(String(64), nullable=True)
    distance_meters = Column(Float, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    # Seconds per completed mile, in order (e.g. [578, 585, 561]); computed
    # on-device from HealthKit distance samples. NULL when unavailable.
    mile_splits = Column(JSON, nullable=True)

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
        # Per-user HealthKit UUID uniqueness so re-imports are idempotent.
        # Same partial-index pattern as client_id (raw sa.text, not a detached
        # Column) so Postgres deploys and test create_all both stay valid.
        Index(
            "ix_workout_sessions_user_hk_uuid_unique",
            "user_id",
            "hk_uuid",
            unique=True,
            postgresql_where=text("hk_uuid IS NOT NULL"),
        ),
    )


class WorkoutExercise(Base):
    """Exercise within a workout session"""
    __tablename__ = "workout_exercises"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String,
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_id = Column(
        String,
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
    workout_exercise_id = Column(
        String,
        ForeignKey("workout_exercises.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    weight = Column(Float, nullable=False)
    weight_unit = Column(Enum(WeightUnit), default=WeightUnit.LB, nullable=False)
    reps = Column(Integer, nullable=False)

    rpe = Column(Integer, nullable=True)  # Rate of Perceived Exertion 1-10
    rir = Column(Integer, nullable=True)  # Reps in Reserve 0-5

    set_number = Column(Integer, nullable=False)  # Order within the exercise
    e1rm = Column(Float, nullable=True)  # Computed estimated 1RM

    # ── Set timing + heart-rate (for per-set exertion analytics) ──
    # `start_time`/`end_time` bound the set so HR samples can be attributed to
    # it. The Apple Watch app records exact boundaries live; the WHOOP backfill
    # path infers them post-hoc from set ordering + created_at and stores them
    # here so the attribution is transparent and editable. avg/peak HR are
    # rolled up from the samples that fall inside [start_time, end_time].
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    avg_heart_rate = Column(Integer, nullable=True)
    peak_heart_rate = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    workout_exercise = relationship("WorkoutExercise", back_populates="sets")


class HeartRateSample(Base):
    """
    Raw heart-rate sample tied to a workout session (and optionally a set).

    Storing raw samples alongside the rolled-up summaries on WorkoutSession/Set
    lets us recompute per-set exertion metrics as the analytics evolve without
    re-ingesting from the wearable. Samples arrive from the Apple Watch
    companion app (live, ~1 Hz) or from the WHOOP API HR series (post-workout).
    """
    __tablename__ = "heart_rate_samples"
    __table_args__ = (
        Index("ix_heart_rate_samples_session_ts", "session_id", "timestamp"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(
        String,
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: a sample may not align to a specific set (e.g. rest periods, or
    # before per-set boundaries are computed). ondelete SET NULL keeps the
    # sample if a set is removed.
    set_id = Column(
        String,
        ForeignKey("sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    timestamp = Column(DateTime, nullable=False)  # UTC
    bpm = Column(Integer, nullable=False)
    source = Column(String, nullable=False)  # "apple_watch" | "whoop"

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
