"""AuditLog model for tracking sensitive operations."""

import uuid

from sqlalchemy import Column, String, Boolean, DateTime, Text
from app.core.types import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class AuditLog(Base):
    """Audit log for OAuth token usage, AI calls, syncs, etc."""

    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Who / what
    user_id = Column(String, nullable=True, index=True)
    action_type = Column(String, nullable=False)
    integration_id = Column(String, nullable=True, index=True)

    # Result
    success = Column(Boolean, nullable=False, default=True)
    error_details = Column(Text, nullable=True)

    # Structured metadata (never includes token values)
    metadata_ = Column("metadata", JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )
