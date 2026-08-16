"""Family member — claimed once via the name picker, no credentials."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String

from app.core.database import Base


class Member(Base):
    __tablename__ = "members"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    color = Column(String, nullable=False, default="#0B7285")
    created_at = Column(DateTime, default=datetime.utcnow)
