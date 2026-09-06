"""Grant the owner unlimited screenshot scans (break-glass fallback).

Run from fitness-app/backend:
    SEED_USER_EMAIL=<owner email> venv/bin/python scripts/grant_owner_unlimited_scans.py

Prefer the owner console (``/admin/ui``); this script is the fallback and
goes through the same service the console uses: it grants a
``scans.unlimited`` entitlement (``source = admin_grant``), which is the one
path that may set ``scan_balances.has_unlimited`` (control-plane spec §6.2),
and writes a system audit row. Idempotent — a second run reports the user
already unlimited. Never prints the email.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: E402, F401 — register every model
from app.models.entitlement import EntitlementSource  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import entitlement_service  # noqa: E402
from app.services.audit_service import audit  # noqa: E402

REASON = "break-glass: scripts/grant_owner_unlimited_scans.py"


def grant_owner_unlimited(session: Session, email: str) -> Dict[str, Any]:
    """Grant ``scans.unlimited`` to the active user with ``email``.

    Returns ``{"user_id", "changed", "has_unlimited", "credits"}``. Raises
    ``LookupError`` when no active user matches. Commits.
    """
    user = (
        session.query(User)
        .filter(User.email == email, User.is_deleted == False)
        .first()
    )
    if user is None:
        raise LookupError("no active user matches SEED_USER_EMAIL")

    key = entitlement_service.KEY_UNLIMITED
    changed = not entitlement_service.is_entitled(session, user.id, key)
    if changed:
        entitlement_service.grant(
            session,
            user_id=user.id,
            key=key,
            value=True,
            source=EntitlementSource.ADMIN_GRANT,
            reason=REASON,
        )
        audit(
            session,
            actor=None,
            action="entitlement.grant",
            target_type="user",
            target_id=user.id,
            after={"key": key, "value": True, "source": EntitlementSource.ADMIN_GRANT.value},
            reason=REASON,
        )
    else:
        # Already granted: just make sure the cached flag agrees.
        entitlement_service.sync_unlimited_flag(session, user.id)
    session.commit()

    balance = entitlement_service.get_or_create_balance(session, user.id)
    return {
        "user_id": user.id,
        "changed": changed,
        "has_unlimited": bool(balance.has_unlimited),
        "credits": balance.scan_credits,
    }


def main() -> int:
    email = (os.environ.get("SEED_USER_EMAIL") or "").strip()
    if not email:
        print("SEED_USER_EMAIL not set — nothing to do")
        return 1
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set")
        return 1

    session = sessionmaker(bind=create_engine(url))()
    try:
        result = grant_owner_unlimited(session, email)
    except LookupError as exc:
        print(str(exc))
        return 1
    finally:
        session.close()
    print(f"user …{result['user_id'][-4:]} has_unlimited={result['has_unlimited']} "
          f"credits={result['credits']}")
    if not result["changed"]:
        print("already unlimited — no change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
