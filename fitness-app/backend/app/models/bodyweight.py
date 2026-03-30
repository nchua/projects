"""
Bodyweight tracking model
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class BodyweightEntry(Base):
    """Daily bodyweight entry"""
    __tablename__ = "bodyweight_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    date = Column(Date, nullable=False, index=True)
    weight_lb = Column(Float, nullable=False)  # Always store in pounds for consistency

    source = Column(String, default="manual", nullable=False)  # manual, apple_health, etc.

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="bodyweight_entries")
