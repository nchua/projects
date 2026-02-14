"""
Screenshot usage tracking model for rate limiting
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from datetime import datetime
import uuid
from app.core.database import Base


class ScreenshotUsage(Base):
    """Tracks screenshot processing usage per user for rate limiting"""
    __tablename__ = "screenshot_usage"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    screenshots_count = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
