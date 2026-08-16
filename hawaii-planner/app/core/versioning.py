"""Global version counter helpers — every mutation bumps, clients poll."""
from sqlalchemy.orm import Session

from app.models.app_state import AppState


def _row(db: Session) -> AppState:
    row = db.get(AppState, 1)
    if row is None:
        row = AppState(id=1, version=1)
        db.add(row)
        db.flush()
    return row


def current_version(db: Session) -> int:
    return _row(db).version


def bump_version(db: Session) -> int:
    """Increment and return the new version. Caller commits."""
    row = _row(db)
    row.version += 1
    return row.version
