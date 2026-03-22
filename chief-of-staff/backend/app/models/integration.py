"""Integration model for external service connections."""

import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Integration(Base):
    """An OAuth integration with an external service."""

    __tablename__ = "integrations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    provider = Column(String, nullable=False)  # IntegrationProvider enum
    scopes = Column(String, nullable=True)

    # Encrypted OAuth tokens
    encrypted_auth_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)

    # Health tracking
    status = Column(String, nullable=False, default="healthy")  # IntegrationStatus
    error_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Rate limiting
    rate_limit_remaining = Column(Integer, nullable=True)
    rate_limit_reset_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="integrations")
    sync_states = relationship(
        "SyncState", back_populates="integration", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_integration_user_provider"),
    )
