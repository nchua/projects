"""
Quest models - Daily quest definitions and user progress
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base


class QuestType(str, enum.Enum):
    """Types of quest objectives"""
    TOTAL_REPS = "total_reps"           # Complete X total reps
    COMPOUND_SETS = "compound_sets"     # Do X sets of compound lifts
    WORKOUT_DURATION = "workout_duration"  # Complete workout in under X minutes
    TOTAL_VOLUME = "total_volume"       # Lift X lbs total
    EXERCISE_SPECIFIC = "exercise_specific"  # Do X sets of specific exercise


class QuestDifficulty(str, enum.Enum):
    """Quest difficulty levels"""
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class QuestDefinition(Base):
    """Master list of all possible quests"""
    __tablename__ = "quest_definitions"

    id = Column(String, primary_key=True)  # e.g., "reps_100", "compound_6"
    name = Column(String, nullable=False)  # Display name
    description = Column(String, nullable=False)  # Quest description
    quest_type = Column(String, nullable=False)  # QuestType enum value
    target_value = Column(Integer, nullable=False)  # Target to reach
    target_exercise = Column(String, nullable=True)  # For exercise-specific quests
    xp_reward = Column(Integer, default=25, nullable=False)
    difficulty = Column(String, default="normal", nullable=False)  # easy, normal, hard
    is_daily = Column(Boolean, default=True, nullable=False)  # Daily vs weekly
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user_quests = relationship("UserQuest", back_populates="quest")


class UserQuest(Base):
    """User's assigned quests and their progress"""
    __tablename__ = "user_quests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    quest_id = Column(String, ForeignKey("quest_definitions.id"), nullable=False)

    assigned_date = Column(Date, nullable=False)  # Date quest was assigned
    progress = Column(Integer, default=0, nullable=False)  # Current progress
    is_completed = Column(Boolean, default=False, nullable=False)
    is_claimed = Column(Boolean, default=False, nullable=False)

    completed_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    # TODO: Re-enable after migration runs on Railway
    # completed_by_workout_id = Column(String, ForeignKey("workout_sessions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    quest = relationship("QuestDefinition", back_populates="user_quests")
    # completed_by_workout = relationship("WorkoutSession", foreign_keys=[completed_by_workout_id])
