"""Shared FastAPI dependencies."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.member import Member


def get_member(
    x_member_id: str | None = Header(default=None, alias="X-Member-Id"),
    db: Session = Depends(get_db),
) -> Member | None:
    """The acting member, when the client identifies one (attribution)."""
    if not x_member_id:
        return None
    return db.get(Member, x_member_id)


def require_member(member: Member | None = Depends(get_member)) -> Member:
    """For actions that must be attributed (voting)."""
    if member is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "member_required", "message": "Pick your name first."},
        )
    return member
