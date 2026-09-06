"""
Admin authentication and step-up (control-plane spec §4).

``require_admin`` is the router-level dependency for ``/admin/*``: it decodes
the admin token (type ``admin``, audience ``ADMIN_AUDIENCE``) and then reads the
``users`` row fresh on every request — admin status, deletion, and
``token_version`` are DB facts, never trusted from the token. ``get_current_user``
rejects admin tokens automatically (``decode_token`` passes no audience), so
the two token classes cannot cross.

``verify_step_up`` is the password re-check every destructive service
function calls first (§4.5); ``protect_account`` is the 403 for acting on
yourself or on another admin (§8.1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import unauthorized
from app.core.rate_limit import client_ip
from app.core.security import (
    decode_admin_token,
    token_version_matches,
    verify_password_with_rehash,
)
from app.models.user import User

# auto_error=False so a missing/malformed header is OUR 401, not HTTPBearer's 403
# (HTTPBearer itself yields None for a missing header or a non-Bearer scheme).
admin_bearer = HTTPBearer(auto_error=False)


async def require_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(admin_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the acting admin from a Bearer admin token.

    401 for a missing/invalid/expired/revoked token or a missing/deleted
    user; 403 for a valid token whose user is no longer an admin.
    """
    if credentials is None:
        raise unauthorized("Admin credentials required")

    payload = decode_admin_token(credentials.credentials)
    if payload is None:
        raise unauthorized("Invalid admin credentials")

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise unauthorized("Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.is_deleted:
        raise unauthorized("User not found")

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    if not token_version_matches(payload, user):
        raise unauthorized("Admin session has been revoked")

    try:  # pragma: no cover - optional dependency
        import sentry_sdk

        sentry_sdk.set_tag("admin_actor", str(user.id))
    except Exception:
        pass

    request.state.audit_ip = client_ip(request)
    request.state.admin_actor_id = user.id
    # ``GET /admin/me`` reports the token's expiry so the console can count down
    # (``decode_admin_token`` requires ``exp``).
    request.state.admin_token_expires_at = datetime.fromtimestamp(
        int(payload["exp"]), tz=timezone.utc
    )
    return user


def verify_step_up(db: Session, actor: User, password: Optional[str]) -> None:
    """Re-verify the acting admin's password before a destructive action.

    Called as the first line of each destructive service function, so
    nothing is pending in the session when it commits a failed attempt.
    Failures count on ``users.admin_failed_logins`` — the same counter the
    admin login lockout uses, so failed logins against the owner's email
    and step-up typos add up; at ``ADMIN_STEP_UP_FAILURES_TO_REVOKE`` the
    user's ``token_version`` is bumped (the admin session dies) and the
    counter resets.
    """
    if not password:
        raise unauthorized("Password confirmation required")

    ok, _ = verify_password_with_rehash(password, actor.password_hash)
    if ok:
        actor.admin_failed_logins = 0
        db.flush()
        return

    actor.admin_failed_logins += 1
    revoked = False
    if actor.admin_failed_logins >= settings.ADMIN_STEP_UP_FAILURES_TO_REVOKE:
        actor.token_version += 1
        actor.admin_failed_logins = 0
        revoked = True
    db.commit()
    if revoked:
        raise unauthorized("Admin session revoked after repeated failed confirmations")
    raise unauthorized("Incorrect password")


def protect_account(actor: User, user: User) -> None:
    """403 for the acting admin's own account and for every other admin (spec §8.1)."""
    if user.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Refusing to act on your own account"
        )
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Refusing to act on another admin"
        )
