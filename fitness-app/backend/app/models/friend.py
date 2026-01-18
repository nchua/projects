"""
Friend and FriendRequest models for social features
"""
from sqlalchemy import Column, String, Enum, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base


class FriendRequestStatus(str, enum.Enum):
    """Friend request status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FriendRequest(Base):
    """Friend request between users"""
    __tablename__ = "friend_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(FriendRequestStatus), default=FriendRequestStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

    # Constraints
    __table_args__ = (
        UniqueConstraint('sender_id', 'receiver_id', name='uq_friend_request_sender_receiver'),
        Index('ix_friend_request_sender_status', 'sender_id', 'status'),
        Index('ix_friend_request_receiver_status', 'receiver_id', 'status'),
    )


class Friendship(Base):
    """
    Friendship between two users.
    Stored bidirectionally (2 rows per friendship) for easy querying.
    """
    __tablename__ = "friendships"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    friend_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    friend = relationship("User", foreign_keys=[friend_id])

    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'friend_id', name='uq_friendship_user_friend'),
        Index('ix_friendship_user_id', 'user_id'),
        Index('ix_friendship_friend_id', 'friend_id'),
    )
