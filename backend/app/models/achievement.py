"""
Achievement models - Definitions and user unlocks
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class AchievementDefinition(Base):
    """Master list of all possible achievements"""
    __tablename__ = "achievement_definitions"

    id = Column(String, primary_key=True)  # e.g., "first_workout", "bench_225"
    name = Column(String, nullable=False)  # Display name
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)  # strength, consistency, milestone, progression
    icon = Column(String, nullable=False)  # SF Symbol name
    xp_reward = Column(Integer, default=50, nullable=False)
    rarity = Column(String, default="common", nullable=False)  # common, rare, epic, legendary

    # Achievement criteria (stored as simple values for common checks)
    requirement_type = Column(String, nullable=True)  # workout_count, weight_lifted, level_reached, etc.
    requirement_value = Column(Integer, nullable=True)  # The target value
    requirement_exercise = Column(String, nullable=True)  # For exercise-specific achievements (e.g., "bench_press")

    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user_achievements = relationship("UserAchievement", back_populates="achievement")


class UserAchievement(Base):
    """Achievements unlocked by users"""
    __tablename__ = "user_achievements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    user_progress_id = Column(String, ForeignKey("user_progress.id"), nullable=False)
    achievement_id = Column(String, ForeignKey("achievement_definitions.id"), nullable=False)

    unlocked_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user_progress = relationship("UserProgress", back_populates="achievements")
    achievement = relationship("AchievementDefinition", back_populates="user_achievements")
