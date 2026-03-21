from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.inbox import InboxItem, InboxStatus
from app.models.learning_unit import LearningUnit
from app.models.source import Source
from app.schemas.inbox import InboxItemResponse, InboxAction

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("", response_model=list[InboxItemResponse])
def list_inbox(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List pending inbox items for review."""
    items = (
        db.query(InboxItem)
        .filter(InboxItem.user_id == user.id, InboxItem.status == InboxStatus.PENDING)
        .order_by(InboxItem.created_at.desc())
        .all()
    )

    results = []
    for item in items:
        unit = db.query(LearningUnit).filter(LearningUnit.id == item.learning_unit_id).first()
        if not unit:
            continue

        source_name = None
        if unit.source_id:
            source = db.query(Source).filter(Source.id == unit.source_id).first()
            source_name = source.name if source else None

        results.append(
            InboxItemResponse(
                id=item.id,
                learning_unit_id=item.learning_unit_id,
                confidence_score=item.confidence_score,
                status=item.status,
                created_at=item.created_at,
                front_content=unit.front_content,
                back_content=unit.back_content,
                unit_type=unit.type,
                source_name=source_name,
            )
        )

    return results


@router.put("/{item_id}", response_model=InboxItemResponse)
def action_inbox_item(
    item_id: int,
    req: InboxAction,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accept or reject an inbox item."""
    item = (
        db.query(InboxItem)
        .filter(InboxItem.id == item_id, InboxItem.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Inbox item not found")

    item.status = req.status

    unit = db.query(LearningUnit).filter(LearningUnit.id == item.learning_unit_id).first()

    if req.status == InboxStatus.ACCEPTED and unit:
        unit.auto_accepted = True
        unit.next_review_at = datetime.now(timezone.utc)
    elif req.status == InboxStatus.REJECTED and unit:
        unit.auto_accepted = False
        unit.next_review_at = None

    db.commit()
    db.refresh(item)

    source_name = None
    if unit and unit.source_id:
        source = db.query(Source).filter(Source.id == unit.source_id).first()
        source_name = source.name if source else None

    return InboxItemResponse(
        id=item.id,
        learning_unit_id=item.learning_unit_id,
        confidence_score=item.confidence_score,
        status=item.status,
        created_at=item.created_at,
        front_content=unit.front_content if unit else "",
        back_content=unit.back_content if unit else "",
        unit_type=unit.type if unit else "concept",
        source_name=source_name,
    )
