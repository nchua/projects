"""
WHOOP OAuth connection model.

Stores a user's WHOOP API tokens so the backend can pull their recent workouts
(avg/peak HR, strain, kJ, HR-zone durations) post-workout and backfill the app's
WorkoutSession HR summary.

Tokens are encrypted at rest with Fernet (keyed off SECRET_KEY — see
``app/core/crypto.py``). The ciphertext lives in the ``*_encrypted`` columns;
the ``access_token`` / ``refresh_token`` Python properties transparently
encrypt on set and decrypt on get so callers work with plaintext.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.core.crypto import decrypt_token, encrypt_token
from app.core.database import Base


class WhoopConnection(Base):
    """A user's WHOOP OAuth credentials (one per user)."""
    __tablename__ = "whoop_connections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # One WHOOP connection per user. unique=True enforces it; ondelete CASCADE
    # removes the connection if the user is hard-deleted.
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Ciphertext (Fernet). Never store the plaintext token in the DB.
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)

    expires_at = Column(DateTime, nullable=True)  # access-token expiry (UTC)
    whoop_user_id = Column(String, nullable=True, index=True)  # WHOOP's user id
    scope = Column(String, nullable=True)  # granted OAuth scopes (space-sep)

    # Provenance / freshness tracking.
    last_synced_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="whoop_connection")

    # ── Transparent encrypt/decrypt of tokens ──
    @property
    def access_token(self) -> Optional[str]:
        return decrypt_token(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value: Optional[str]) -> None:
        self.access_token_encrypted = encrypt_token(value)

    @property
    def refresh_token(self) -> Optional[str]:
        return decrypt_token(self.refresh_token_encrypted)

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        self.refresh_token_encrypted = encrypt_token(value)
