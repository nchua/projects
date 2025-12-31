"""
Personal Record (PR) tracking model
"""
from sqlalchemy import Column, String, Float, Integer, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base


class PRType(str, enum.Enum):
    """Type of personal record"""
    E1RM = "e1rm"  # Estimated 1RM PR
    REP_PR = "rep_pr"  # Rep PR at a given weight


class PR(Base):
    """Personal record achievement"""
    __tablename__ = "prs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    exercise_id = Column(String, ForeignKey("exercises.id"), nullable=False, index=True)

    pr_type = Column(Enum(PRType), nullable=False)

    # For e1RM PRs
    value = Column(Float, nullable=True)  # e1RM value

    # For rep PRs
    reps = Column(Integer, nullable=True)  # Number of reps
    weight = Column(Float, nullable=True)  # Weight at which reps were achieved

    achieved_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="prs")
    exercise = relationship("Exercise", back_populates="prs")
