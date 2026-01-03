"""
Daily Activity model for HealthKit sync
"""
from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class DailyActivity(Base):
    """Daily activity entry from HealthKit or other sources"""
    __tablename__ = "daily_activity"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    date = Column(Date, nullable=False, index=True)
    source = Column(String, default="apple_fitness", nullable=False)

    # Core metrics
    steps = Column(Integer, nullable=True)
    active_calories = Column(Integer, nullable=True)
    total_calories = Column(Integer, nullable=True)
    active_minutes = Column(Integer, nullable=True)

    # Apple Fitness rings
    exercise_minutes = Column(Integer, nullable=True)  # Green ring
    stand_hours = Column(Integer, nullable=True)  # Blue ring
    move_calories = Column(Integer, nullable=True)  # Red ring

    # Whoop/other wearables
    strain = Column(Float, nullable=True)
    recovery_score = Column(Integer, nullable=True)
    hrv = Column(Integer, nullable=True)
    resting_heart_rate = Column(Integer, nullable=True)
    sleep_hours = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="daily_activities")

    # Ensure one entry per date per source per user
    __table_args__ = (
        UniqueConstraint('user_id', 'date', 'source', name='unique_user_date_source'),
    )
