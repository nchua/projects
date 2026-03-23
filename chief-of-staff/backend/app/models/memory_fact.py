"""MemoryFact model — bi-temporal contextual memory (Mem0 + Zep pattern)."""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.types import JSONB


class MemoryFact(Base):
    """A contextual fact extracted from messages/meetings.

    Uses bi-temporal timestamps (Zep pattern) and supersession
    tracking (Mem0 pattern) for memory lifecycle management.
    """

    __tablename__ = "memory_facts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Core content
    fact_text = Column(Text, nullable=False)
    fact_type = Column(String, nullable=False)
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    people = Column(JSONB, nullable=True)

    # Bi-temporal (Zep pattern) — never hard-delete
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    extracted_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    invalidated_at = Column(DateTime(timezone=True), nullable=True)

    # Relevance scoring (exponential decay)
    importance = Column(Float, nullable=False, default=0.5)
    access_count = Column(Integer, nullable=False, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

    # Mem0 supersession tracking
    superseded_by_id = Column(
        String, ForeignKey("memory_facts.id"), nullable=True
    )
    is_active = Column(Boolean, nullable=False, default=True)

    dedup_hash = Column(String, nullable=True, index=True)
    confidence = Column(Float, nullable=False, default=0.5)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="memory_facts")
    superseded_by = relationship(
        "MemoryFact", remote_side=[id], foreign_keys=[superseded_by_id]
    )
