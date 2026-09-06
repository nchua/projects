"""
Startup tasks for the owner console (control-plane spec §4.1, §8.3).

``bootstrap_admin`` is the only path that sets ``users.is_admin = true``: it
promotes the existing, non-deleted account whose email matches
``ADMIN_BOOTSTRAP_EMAIL`` (case-insensitively, exactly one match) and writes
an audit row. It runs on every boot, so setting the variable after the first
deploy still works; consequently, demoting the bootstrap account means
removing the variable and redeploying.

``run_startup_tasks`` is called from the FastAPI lifespan and never raises.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.services.audit_service import audit

logger = logging.getLogger(__name__)


def bootstrap_admin(db: Session) -> Optional[str]:
    """Promote the bootstrap account if needed. Returns the promoted user id,
    or None when nothing changed (unset var, no match, collision, already admin)."""
    email = (settings.ADMIN_BOOTSTRAP_EMAIL or "").strip()
    if not email:
        return None

    matches = (
        db.query(User)
        .filter(func.lower(User.email) == email.lower(), User.is_deleted == False)
        .all()
    )
    if not matches:
        logger.error("admin bootstrap: ADMIN_BOOTSTRAP_EMAIL matches no active account — nobody is admin")
        return None
    if len(matches) > 1:
        logger.error(
            "admin bootstrap: ADMIN_BOOTSTRAP_EMAIL matches %d accounts (case collision) — skipped",
            len(matches),
        )
        return None

    user = matches[0]
    if user.is_admin:
        return None

    user.is_admin = True
    audit(
        db,
        actor=None,
        action="admin.bootstrap",
        target_type="user",
        target_id=user.id,
        before={"is_admin": False},
        after={"is_admin": True},
        reason="ADMIN_BOOTSTRAP_EMAIL",
    )
    db.commit()
    logger.info("admin bootstrap: promoted user …%s", user.id[-4:])
    return user.id


def run_startup_tasks() -> None:
    """Lifespan hook: bootstrap the admin. Never raises, never blocks boot."""
    from app.core import database  # resolved at call time so tests can patch SessionLocal

    try:
        db = database.SessionLocal()
        try:
            bootstrap_admin(db)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - startup must not fail on this
        logger.exception("admin bootstrap failed")
