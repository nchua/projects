"""
Admin audit helper (control-plane spec §5).

``audit()`` adds the row and flushes — it never commits — so the caller's
commit persists the change and its audit row together, and a failure after
``audit()`` rolls both back. Callers pass allow-listed snapshots
(:func:`snapshot`); the payload is scrubbed here against a key denylist so a
mistaken allow-list still cannot leak a hash, a token, or a reset code.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Iterable, Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.request_context import get_request_id
from app.models.admin import AdminAuditLog
from app.models.user import User

logger = logging.getLogger(__name__)

# Keys that never belong in an audit payload, matched by shape: exact names
# for the obvious secrets, suffixes for credential-bearing columns
# (``whoop_token``, ``access_token_encrypted``, ``password_hash``). Plain
# counters such as ``token_version`` do not match and are kept.
_DENY_EXACT = {"password", "password_hash", "code", "token", "secret", "secret_key", "email"}
_DENY_SUFFIX = ("_token", "_encrypted", "_secret", "_hash")


def _denied(key: str) -> bool:
    k = key.lower()
    return k in _DENY_EXACT or k.endswith(_DENY_SUFFIX)


def _drop_denied(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if _denied(str(k)):
                logger.debug("audit scrub dropped key %s", k)
                continue
            out[str(k)] = _drop_denied(v)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_drop_denied(v) for v in value]
    return value


def scrub(payload: Optional[Any]) -> Optional[Any]:
    """Drop denylisted keys recursively and make the payload JSON-safe."""
    if payload is None:
        return None
    return jsonable_encoder(_drop_denied(payload))


def snapshot(obj: Any, fields: Iterable[str]) -> Dict[str, Any]:
    """Allow-listed, JSON-safe snapshot of ``fields`` on ``obj``."""
    return scrub({f: getattr(obj, f, None) for f in fields})


def body_hash(payload: Dict[str, Any]) -> str:
    """Stable SHA-256 of a request body (for idempotency replay checks)."""
    canonical = json.dumps(scrub(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def audit(
    db: Session,
    *,
    actor: Optional[User],
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
    request: Optional[Request] = None,
    idempotency_key: Optional[str] = None,
    body_sha256: Optional[str] = None,
) -> AdminAuditLog:
    """Add one audit row to the current transaction (flush, no commit)."""
    request_id = get_request_id()
    row = AdminAuditLog(
        actor_user_id=actor.id if actor is not None else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=scrub(before),
        after=scrub(after),
        reason=reason,
        request_id=None if request_id == "-" else request_id,
        ip=getattr(request.state, "audit_ip", None) if request is not None else None,
        idempotency_key=idempotency_key,
        body_sha256=body_sha256,
    )
    db.add(row)
    db.flush()
    return row
