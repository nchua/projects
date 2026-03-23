"""Contact and ActionItemContact association models."""

import uuid

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Contact(Base):
    """A person referenced in action items or reminders."""

    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    display_name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    slack_id = Column(String, nullable=True)
    github_username = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    last_interaction_at = Column(DateTime(timezone=True), nullable=True)

    # Scoring columns for adaptive prioritization
    interaction_count = Column(Integer, nullable=False, default=0)
    action_item_count = Column(Integer, nullable=False, default=0)
    dismissal_count = Column(Integer, nullable=False, default=0)
    importance_score = Column(Float, nullable=False, default=0.5)

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="contacts")
    action_item_links = relationship(
        "ActionItemContact", back_populates="contact", cascade="all, delete-orphan"
    )


class ActionItemContact(Base):
    """Association table linking action items to contacts."""

    __tablename__ = "action_item_contacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    action_item_id = Column(
        String, ForeignKey("action_items.id"), nullable=False, index=True
    )
    contact_id = Column(
        String, ForeignKey("contacts.id"), nullable=False, index=True
    )

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )

    # Relationships
    action_item = relationship("ActionItem", back_populates="contact_links")
    contact = relationship("Contact", back_populates="action_item_links")

    __table_args__ = (
        UniqueConstraint(
            "action_item_id", "contact_id", name="uq_action_item_contact"
        ),
    )
