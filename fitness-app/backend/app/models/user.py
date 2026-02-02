"""
User and UserProfile models
"""
from sqlalchemy import Column, String, Integer, Float, Enum, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base


class TrainingExperience(str, enum.Enum):
    """Training experience levels"""
    BEGINNER = "beginner"
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    ELITE = "elite"


class WeightUnit(str, enum.Enum):
    """Weight units"""
    LB = "lb"
    KG = "kg"


class E1RMFormula(str, enum.Enum):
    """e1RM calculation formulas"""
    EPLEY = "epley"
    BRZYCKI = "brzycki"
    WATHAN = "wathan"
    LOMBARDI = "lombardi"


class User(Base):
    """User account"""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String(20), unique=True, nullable=True, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    workout_sessions = relationship("WorkoutSession", back_populates="user", cascade="all, delete-orphan")
    custom_exercises = relationship("Exercise", back_populates="user", cascade="all, delete-orphan")
    bodyweight_entries = relationship("BodyweightEntry", back_populates="user", cascade="all, delete-orphan")
    prs = relationship("PR", back_populates="user", cascade="all, delete-orphan")
    daily_activities = relationship("DailyActivity", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    weekly_missions = relationship("WeeklyMission", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    """User profile with settings and body metrics"""
    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)

    # Body metrics
    age = Column(Integer, nullable=True)
    sex = Column(String, nullable=True)  # 'M' or 'F'
    bodyweight_lb = Column(Float, nullable=True)
    height_inches = Column(Float, nullable=True)  # Height in inches

    # Training settings
    training_experience = Column(Enum(TrainingExperience), default=TrainingExperience.BEGINNER)
    preferred_unit = Column(Enum(WeightUnit), default=WeightUnit.LB)
    e1rm_formula = Column(Enum(E1RMFormula), default=E1RMFormula.EPLEY)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="profile")
