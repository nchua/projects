"""
User Progress model - XP, leveling, and rank tracking
"""
from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, date
import uuid
import enum
from app.core.database import Base


class HunterRank(str, enum.Enum):
    """Solo Leveling inspired hunter ranks"""
    E = "E"
    D = "D"
    C = "C"
    B = "B"
    A = "A"
    S = "S"


class UserProgress(Base):
    """User's XP, level, and rank progression"""
    __tablename__ = "user_progress"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)

    # XP and Leveling
    total_xp = Column(Integer, default=0, nullable=False)
    level = Column(Integer, default=1, nullable=False)
    rank = Column(String, default="E", nullable=False)  # E, D, C, B, A, S

    # Streak tracking
    current_streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)
    last_workout_date = Column(Date, nullable=True)

    # Stats
    total_workouts = Column(Integer, default=0, nullable=False)
    total_volume_lb = Column(Integer, default=0, nullable=False)  # Lifetime volume
    total_prs = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", backref="progress")
    achievements = relationship("UserAchievement", back_populates="user_progress", cascade="all, delete-orphan")
