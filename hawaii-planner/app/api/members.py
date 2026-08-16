"""Name-picker identity: idempotent claims, no credentials."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.serialize import member_out
from app.core.database import get_db
from app.core.versioning import bump_version
from app.models.member import Member
from app.schemas.member import MemberClaim

router = APIRouter()

# Assigned round-robin to new members; seeded members carry curated colors.
MEMBER_COLORS = [
    "#0B7285",  # ocean
    "#D6336C",  # hibiscus
    "#2F9E44",  # palm
    "#E8A13C",  # amber
    "#1864AB",  # deep ocean
    "#C2255C",  # sunset
    "#C9A227",  # cane
]


@router.get("/api/members")
def list_members(db: Session = Depends(get_db)) -> dict:
    members = db.query(Member).order_by(Member.created_at).all()
    return {"members": [member_out(member) for member in members]}


@router.post("/api/members")
def claim_member(
    body: MemberClaim, response: Response, db: Session = Depends(get_db)
) -> dict:
    """Case-insensitive idempotent claim: existing name returns that member
    (200); a new name creates one (201)."""
    name = body.name.strip()
    existing = (
        db.query(Member).filter(func.lower(Member.name) == name.lower()).first()
    )
    if existing is not None:
        return {"member": member_out(existing), "created": False}

    color = MEMBER_COLORS[db.query(Member).count() % len(MEMBER_COLORS)]
    member = Member(name=name, color=color)
    db.add(member)
    version = bump_version(db)
    db.commit()
    response.status_code = 201
    return {"member": member_out(member), "created": True, "version": version}
