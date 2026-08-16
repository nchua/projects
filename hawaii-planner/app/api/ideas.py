"""Idea pool CRUD and voting (activities + restaurants share everything)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_member, require_member
from app.api.errors import bad_request, not_found, reject_null_fields
from app.api.serialize import idea_out, scheduled_day_ids_by_idea
from app.core.database import get_db
from app.core.versioning import bump_version
from app.models.idea import (
    MUST_GO_BUDGET_PER_BOARD,
    VOTE_MUST_GO,
    Idea,
    Vote,
)
from app.models.member import Member
from app.models.region import Region
from app.schemas.idea import IdeaCreate, IdeaPatch, VoteIn

router = APIRouter()


def _get_idea(db: Session, idea_id: str) -> Idea:
    idea = (
        db.query(Idea)
        .options(joinedload(Idea.votes))
        .filter(Idea.id == idea_id)
        .first()
    )
    if idea is None:
        raise not_found("idea_not_found", "That idea no longer exists.")
    return idea


def _idea_response(db: Session, idea: Idea, version: int) -> dict:
    day_ids = scheduled_day_ids_by_idea(db).get(idea.id, [])
    return {"version": version, "idea": idea_out(idea, day_ids)}


def _validate_region(db: Session, region_id: str) -> None:
    if db.get(Region, region_id) is None:
        raise bad_request(f"Unknown region {region_id!r}.", code="unknown_region")


@router.post("/api/ideas", status_code=201)
def create_idea(
    body: IdeaCreate,
    db: Session = Depends(get_db),
    member: Member | None = Depends(get_member),
) -> dict:
    _validate_region(db, body.region_id)
    idea = Idea(
        title=body.title.strip(),
        kind=body.kind,
        region_id=body.region_id,
        duration_min=body.duration_min
        or (75 if body.kind == "restaurant" else 90),
        yelp_url=body.yelp_url,
        maps_url=body.maps_url,
        notes=body.notes,
        best_time=body.best_time,
        meal_tags=",".join(body.meal_tags),
        created_by_member_id=member.id if member else None,
    )
    db.add(idea)
    version = bump_version(db)
    db.commit()
    return _idea_response(db, idea, version)


@router.patch("/api/ideas/{idea_id}")
def patch_idea(idea_id: str, body: IdeaPatch, db: Session = Depends(get_db)) -> dict:
    idea = _get_idea(db, idea_id)
    updates = body.model_dump(exclude_unset=True)
    reject_null_fields(updates, ("title", "region_id", "duration_min"))
    if "region_id" in updates:
        _validate_region(db, updates["region_id"])
    if "meal_tags" in updates and updates["meal_tags"] is not None:
        updates["meal_tags"] = ",".join(updates["meal_tags"])
    for field, value in updates.items():
        setattr(idea, field, value)
    version = bump_version(db)
    db.commit()
    return _idea_response(db, idea, version)


@router.delete("/api/ideas/{idea_id}")
def delete_idea(idea_id: str, db: Session = Depends(get_db)) -> dict:
    idea = _get_idea(db, idea_id)
    db.delete(idea)  # ORM cascade removes votes + schedule items
    version = bump_version(db)
    db.commit()
    return {"version": version, "deleted": idea_id}


@router.put("/api/ideas/{idea_id}/vote")
def set_vote(
    idea_id: str,
    body: VoteIn,
    db: Session = Depends(get_db),
    member: Member = Depends(require_member),
) -> dict:
    idea = _get_idea(db, idea_id)

    if body.value == VOTE_MUST_GO:
        # Budget: 3 must-go stars per member per board (board = idea.kind).
        current = (
            db.query(Vote)
            .join(Idea, Vote.idea_id == Idea.id)
            .filter(
                Vote.member_id == member.id,
                Vote.value == VOTE_MUST_GO,
                Idea.kind == idea.kind,
                Vote.idea_id != idea.id,
            )
            .all()
        )
        if len(current) >= MUST_GO_BUDGET_PER_BOARD:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "must_go_budget_exceeded",
                    "message": (
                        f"You've used your {MUST_GO_BUDGET_PER_BOARD} must-go stars "
                        "— move one first."
                    ),
                    "current_must_go_idea_ids": [vote.idea_id for vote in current],
                },
            )

    vote = db.get(Vote, {"idea_id": idea.id, "member_id": member.id})
    if vote is None:
        db.add(Vote(idea_id=idea.id, member_id=member.id, value=body.value))
    else:
        vote.value = body.value
    version = bump_version(db)
    db.commit()
    db.refresh(idea)
    return _idea_response(db, idea, version)


@router.delete("/api/ideas/{idea_id}/vote")
def clear_vote(
    idea_id: str,
    db: Session = Depends(get_db),
    member: Member = Depends(require_member),
) -> dict:
    idea = _get_idea(db, idea_id)
    vote = db.get(Vote, {"idea_id": idea.id, "member_id": member.id})
    if vote is not None:
        db.delete(vote)
    version = bump_version(db)
    db.commit()
    db.refresh(idea)
    return _idea_response(db, idea, version)
