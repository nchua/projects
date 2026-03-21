from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.topic import Topic
from app.models.concept import Concept
from app.models.learning_unit import LearningUnit
from app.models.inbox import InboxItem, InboxStatus
from app.models.source import Source
from app.schemas.learning_unit import (
    LearningUnitCreate,
    LearningUnitUpdate,
    LearningUnitResponse,
    ReviewCardResponse,
)

router = APIRouter(prefix="/learning-units", tags=["learning_units"])

AUTO_ACCEPT_THRESHOLD = 0.85


@router.get("", response_model=list[LearningUnitResponse])
def list_units(
    concept_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List learning units, optionally filtered by concept."""
    query = (
        db.query(LearningUnit)
        .join(Concept)
        .join(Topic)
        .filter(Topic.user_id == user.id)
    )
    if concept_id is not None:
        query = query.filter(LearningUnit.concept_id == concept_id)
    return query.all()


@router.post("", response_model=LearningUnitResponse, status_code=201)
def create_unit(
    req: LearningUnitCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a learning unit (card).

    If confidence_score is provided (AI-generated), routes through inbox:
    - score >= 0.85: auto-accepted
    - score < 0.85: pending in inbox for manual review
    """
    # Verify concept belongs to user
    concept = (
        db.query(Concept)
        .join(Topic)
        .filter(Concept.id == req.concept_id, Topic.user_id == user.id)
        .first()
    )
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    unit = LearningUnit(
        concept_id=req.concept_id,
        type=req.type,
        front_content=req.front_content,
        back_content=req.back_content,
        source_id=req.source_id,
        ai_generated=req.ai_generated,
    )

    # Handle inbox routing for AI-generated cards
    if req.confidence_score is not None:
        auto_accept = req.confidence_score >= AUTO_ACCEPT_THRESHOLD
        unit.auto_accepted = auto_accept

        db.add(unit)
        db.flush()  # get unit.id

        inbox_item = InboxItem(
            learning_unit_id=unit.id,
            user_id=user.id,
            confidence_score=req.confidence_score,
            status=InboxStatus.ACCEPTED if auto_accept else InboxStatus.PENDING,
        )
        db.add(inbox_item)

        # Auto-accepted cards are immediately schedulable
        if auto_accept:
            unit.next_review_at = datetime.now(timezone.utc)
    else:
        # Manual cards — immediately schedulable
        unit.auto_accepted = True
        unit.next_review_at = datetime.now(timezone.utc)
        db.add(unit)

    db.commit()
    db.refresh(unit)
    return unit


@router.get("/due", response_model=list[ReviewCardResponse])
def get_due_cards(
    limit: int = Query(default=30, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get cards due for review, ordered by priority.

    Respects the daily review cap (default 30).
    """
    now = datetime.now(timezone.utc)

    units = (
        db.query(LearningUnit, Topic.name.label("topic_name"))
        .select_from(LearningUnit)
        .join(Concept, LearningUnit.concept_id == Concept.id)
        .join(Topic, Concept.topic_id == Topic.id)
        .filter(
            Topic.user_id == user.id,
            LearningUnit.auto_accepted == True,  # noqa: E712
            LearningUnit.next_review_at.isnot(None),
            LearningUnit.next_review_at <= now.replace(tzinfo=None),
        )
        .order_by(LearningUnit.next_review_at.asc())
        .limit(limit)
        .all()
    )

    results = []
    for unit, topic_name in units:
        source_name = None
        if unit.source_id:
            source = db.query(Source).filter(Source.id == unit.source_id).first()
            source_name = source.name if source else None

        results.append(
            ReviewCardResponse(
                id=unit.id,
                concept_id=unit.concept_id,
                type=unit.type,
                front_content=unit.front_content,
                back_content=unit.back_content,
                topic_name=topic_name,
                source_name=source_name,
            )
        )

    return results


@router.get("/{unit_id}", response_model=LearningUnitResponse)
def get_unit(
    unit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single learning unit."""
    unit = (
        db.query(LearningUnit)
        .join(Concept)
        .join(Topic)
        .filter(LearningUnit.id == unit_id, Topic.user_id == user.id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Learning unit not found")
    return unit


@router.put("/{unit_id}", response_model=LearningUnitResponse)
def update_unit(
    unit_id: int,
    req: LearningUnitUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a learning unit's content."""
    unit = (
        db.query(LearningUnit)
        .join(Concept)
        .join(Topic)
        .filter(LearningUnit.id == unit_id, Topic.user_id == user.id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Learning unit not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)

    db.commit()
    db.refresh(unit)
    return unit


@router.delete("/{unit_id}", status_code=204)
def delete_unit(
    unit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a learning unit."""
    unit = (
        db.query(LearningUnit)
        .join(Concept)
        .join(Topic)
        .filter(LearningUnit.id == unit_id, Topic.user_id == user.id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Learning unit not found")
    db.delete(unit)
    db.commit()
