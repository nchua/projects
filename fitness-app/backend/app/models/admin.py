"""
Admin audit log (control-plane spec §5).

One row per admin mutation, written in the same transaction as the change —
``audit_service.audit`` flushes and never commits, so the caller's commit
persists the change and its audit row together (or rolls both back).

Neither ``actor_user_id`` nor ``target_id`` is a foreign key: the trail must
outlive a purged user, and a cascading SET NULL would itself be an UPDATE
that the append-only trigger below rejects. Append-only: no code path
updates or deletes rows, and the Postgres migration adds a BEFORE UPDATE OR
DELETE trigger that raises.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Index, String, Text, text

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminAuditLog(Base):
    """Immutable record of one admin action."""

    __tablename__ = "admin_audit_log"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id = Column(String, nullable=True)  # NULL = system (bootstrap, sweep)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    request_id = Column(String, nullable=True)
    ip = Column(String, nullable=True)
    # Credits-adjust replay record (spec §7.1): the audit row is the
    # idempotency store; ``body_sha256`` lets a same-key/different-body
    # replay be rejected instead of silently returning the old result.
    idempotency_key = Column(String, nullable=True)
    body_sha256 = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_admin_audit_target", "target_type", "target_id", "created_at"),
        Index("ix_admin_audit_actor", "actor_user_id", "created_at"),
        Index(
            "uq_admin_audit_idempotency",
            "actor_user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )
