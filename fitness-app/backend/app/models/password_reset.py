"""
Password Reset Token model for email-based password reset
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from datetime import datetime
import uuid
import secrets
from app.core.database import Base


def generate_reset_code() -> str:
    """Generate a 6-digit numeric reset code"""
    return str(secrets.randbelow(900000) + 100000)


class PasswordResetToken(Base):
    """Password reset token for email verification"""
    __tablename__ = "password_reset_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
