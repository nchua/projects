"""
Bodyweight tracking model
"""
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class BodyweightEntry(Base):
    """Daily bodyweight entry"""
    __tablename__ = "bodyweight_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    date = Column(Date, nullable=False, index=True)
    weight_lb = Column(Float, nullable=False)  # Always store in pounds for consistency

    source = Column(String, default="manual", nullable=False)  # manual, apple_health, etc.

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="bodyweight_entries")
