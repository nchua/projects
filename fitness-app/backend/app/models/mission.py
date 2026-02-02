"""
Mission models - AI-powered coaching system with goals and weekly missions
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Date, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base


class GoalStatus(str, enum.Enum):
    """Status of a user's strength goal"""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


class MissionStatus(str, enum.Enum):
    """Status of a weekly mission"""
    OFFERED = "offered"      # Available for user to accept
    ACCEPTED = "accepted"    # User accepted, in progress
    COMPLETED = "completed"  # All workouts completed
    EXPIRED = "expired"      # Week ended without completion
    DECLINED = "declined"    # User explicitly declined


class MissionWorkoutStatus(str, enum.Enum):
    """Status of individual workout within a mission"""
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class Goal(Base):
    """User's strength PR goal"""
    __tablename__ = "goals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    exercise_id = Column(String, ForeignKey("exercises.id"), nullable=False)

    # Target
    target_weight = Column(Float, nullable=False)  # Target weight to lift
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="goals")
    exercise = relationship("Exercise")
    missions = relationship("WeeklyMission", back_populates="goal", cascade="all, delete-orphan")


class WeeklyMission(Base):
    """A week's training mission tied to a goal"""
    __tablename__ = "weekly_missions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=False, index=True)

    # Week boundaries
    week_start = Column(Date, nullable=False)  # Monday of the week
    week_end = Column(Date, nullable=False)    # Sunday of the week

    # Status
    status = Column(String, default="offered", nullable=False)  # MissionStatus
    accepted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    declined_at = Column(DateTime, nullable=True)

    # XP reward
    xp_reward = Column(Integer, default=200, nullable=False)  # Base XP for completing mission
    xp_earned = Column(Integer, default=0, nullable=False)    # Actual XP earned

    # AI-generated context
    weekly_target = Column(String, nullable=True)  # e.g., "Hit 4x5 @ 190 lbs on heavy day"
    coaching_message = Column(Text, nullable=True)  # AI coaching message for the week

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="weekly_missions")
    goal = relationship("Goal", back_populates="missions")
    workouts = relationship("MissionWorkout", back_populates="mission", cascade="all, delete-orphan", order_by="MissionWorkout.day_number")


class MissionWorkout(Base):
    """A prescribed workout within a weekly mission"""
    __tablename__ = "mission_workouts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    mission_id = Column(String, ForeignKey("weekly_missions.id"), nullable=False, index=True)

    # Workout details
    day_number = Column(Integer, nullable=False)  # 1, 2, 3 (order in the week)
    focus = Column(String, nullable=False)  # e.g., "Push - Heavy Bench", "Pull", "Legs"
    primary_lift = Column(String, nullable=True)  # Main lift for this workout

    # Status
    status = Column(String, default="pending", nullable=False)  # MissionWorkoutStatus
    completed_workout_id = Column(String, ForeignKey("workout_sessions.id"), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # AI evaluation
    completion_notes = Column(Text, nullable=True)  # AI notes on how workout matched prescription

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    mission = relationship("WeeklyMission", back_populates="workouts")
    completed_workout = relationship("WorkoutSession")
    prescriptions = relationship("ExercisePrescription", back_populates="mission_workout", cascade="all, delete-orphan", order_by="ExercisePrescription.order_index")


class ExercisePrescription(Base):
    """Prescribed exercise within a mission workout"""
    __tablename__ = "exercise_prescriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    mission_workout_id = Column(String, ForeignKey("mission_workouts.id"), nullable=False, index=True)
    exercise_id = Column(String, ForeignKey("exercises.id"), nullable=False)

    # Prescription
    order_index = Column(Integer, nullable=False)  # Order within workout
    sets = Column(Integer, nullable=False)
    reps = Column(Integer, nullable=False)
    weight = Column(Float, nullable=True)  # Prescribed weight (optional)
    weight_unit = Column(String, default="lb", nullable=False)
    rpe_target = Column(Integer, nullable=True)  # Target RPE 1-10

    # Notes
    notes = Column(Text, nullable=True)  # e.g., "Focus on controlled descent"

    # Completion tracking
    is_completed = Column(Boolean, default=False, nullable=False)
    actual_sets = Column(Integer, nullable=True)  # What user actually did
    actual_reps = Column(Integer, nullable=True)
    actual_weight = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    mission_workout = relationship("MissionWorkout", back_populates="prescriptions")
    exercise = relationship("Exercise")
