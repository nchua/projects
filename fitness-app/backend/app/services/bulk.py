"""
The per-user bulk loop shared by every bulk admin route (console v2 spec §5.4).

``per_user`` runs one ``step`` per id in its own committed transaction and
sorts the outcomes: a ``Skip`` raised inside the step → ``skipped`` with its
reason; an ``HTTPException`` (403 from ``protect_account``, 404, 409 …) or
any other error → a rollback that undoes only that id, then ``failed`` with
the detail. Nothing is rolled back for a sibling's failure (decision 4),
and every audit row a step writes shares the request's ``X-Request-ID``
through ``audit()``. Lives apart from the mutation service so
``purge_service`` can use it without an import cycle.
"""
from __future__ import annotations

from typing import Callable, List, Sequence, Tuple, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import not_found
from app.models.user import User
from app.schemas.admin import BulkFailed, BulkSkipped

T = TypeVar("T")


class Skip(Exception):
    """Raised inside a per-user step to record the id as skipped, not failed."""


def error_text(exc: Exception) -> str:
    """``RuntimeError: message`` — the class alone tells the operator nothing."""
    message = str(exc)
    return f"{exc.__class__.__name__}: {message}" if message else exc.__class__.__name__


def per_user(
    db: Session, user_ids: Sequence[str], step: Callable[[User], T]
) -> Tuple[List[T], List[BulkSkipped], List[BulkFailed]]:
    """Run ``step`` for each id (de-duplicated, in order) in its own committed transaction."""
    applied: List[T] = []
    skipped: List[BulkSkipped] = []
    failed: List[BulkFailed] = []
    for user_id in dict.fromkeys(user_ids):
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user is None:
                raise not_found("User not found")
            result = step(user)
            db.commit()
            applied.append(result)  # only once the commit has succeeded
        except Skip as exc:
            db.rollback()
            skipped.append(BulkSkipped(user_id=user_id, why=str(exc)))
        except HTTPException as exc:
            db.rollback()
            failed.append(BulkFailed(user_id=user_id, error=str(exc.detail)))
        except Exception as exc:  # noqa: BLE001 - a sibling's failure must not stop the batch
            db.rollback()
            failed.append(BulkFailed(user_id=user_id, error=error_text(exc)))
    return applied, skipped, failed
