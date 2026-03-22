"""SyncState model for tracking integration sync cursors."""

import uuid

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class SyncState(Base):
    """Tracks sync cursor/position for an integration resource."""

    __tablename__ = "sync_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(
        String, ForeignKey("integrations.id"), nullable=False, index=True
    )

    resource_type = Column(String, nullable=False)  # ResourceType enum

    # Cursor tracking
    cursor_value = Column(Text, nullable=True)
    cursor_type = Column(String, nullable=True)

    # Last sync info
    last_sync_status = Column(String, nullable=True)  # SyncStatus enum
    last_sync_error = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    integration = relationship("Integration", back_populates="sync_states")

    __table_args__ = (
        UniqueConstraint(
            "integration_id", "resource_type", name="uq_sync_state_integration_resource"
        ),
    )
