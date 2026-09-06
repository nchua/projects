"""
Admin service (control-plane spec §4.2 in W0; user list/detail and the
mutations land in W1–W2). Every mutation here takes the acting admin and
writes its audit row inside the same transaction.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.config import settings
from app.core.dependencies import unauthorized
from app.core.security import (
    create_admin_token,
    hash_password,
    verify_password_with_rehash,
)
from app.core.utils import ensure_utc
from app.models.user import User
from app.services.audit_service import audit


def _generic_unauthorized() -> HTTPException:
    return unauthorized("Incorrect email or password")


def mint_admin_session(
    db: Session,
    *,
    email: str,
    password: str,
    request: Optional[Request] = None,
) -> Tuple[str, datetime]:
    """Verify credentials and mint an admin token (no refresh token).

    401 (generic) for unknown/deleted user or bad password — bad passwords
    count toward the DB lockout; 423 while locked; 403 for a valid password
    on a non-admin account (does not count: ``/auth/login`` already confirms
    password validity, so there is no new oracle). Writes ``session.create``.
    """
    now = datetime.now(timezone.utc)
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.is_deleted:
        raise _generic_unauthorized()

    locked_until = ensure_utc(user.admin_locked_until)
    if locked_until is not None and locked_until > now:
        retry = max(1, int((locked_until - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Admin login temporarily locked. Try again later.",
            headers={"Retry-After": str(retry)},
        )

    ok, needs_rehash = verify_password_with_rehash(password, user.password_hash)
    if not ok:
        user.admin_failed_logins += 1
        if user.admin_failed_logins >= settings.ADMIN_LOCKOUT_THRESHOLD:
            user.admin_locked_until = now + timedelta(minutes=settings.ADMIN_LOCKOUT_MINUTES)
            user.admin_failed_logins = 0
        db.commit()
        raise _generic_unauthorized()

    if needs_rehash:
        user.password_hash = hash_password(password)

    if not user.is_admin:
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    user.admin_failed_logins = 0
    user.admin_locked_until = None
    token, expires_at = create_admin_token(user)
    audit(
        db,
        actor=user,
        action="session.create",
        target_type="user",
        target_id=user.id,
        after={"expires_at": expires_at},
        request=request,
    )
    db.commit()
    return token, expires_at
