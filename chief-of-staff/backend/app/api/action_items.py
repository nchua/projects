"""Action item API endpoints — CRUD + dismiss/acknowledge/action."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.action_item import ActionItem
from app.models.enums import (
    ActionItemStatus,
)
from app.models.user import User
from app.schemas.action_item import (
    ActionItemCreate,
    ActionItemDismiss,
    ActionItemResponse,
    ActionItemSnooze,
)
from app.services.feedback_service import (
    dismiss_action_item,
    get_dismissal_stats,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Default pagination
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@router.get("", response_model=list[ActionItemResponse])
def list_action_items(
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
    source: Optional[str] = Query(
        None, description="Filter by source"
    ),
    priority: Optional[str] = Query(
        None, description="Filter by priority"
    ),
    limit: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE
    ),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActionItemResponse]:
    """List action items with optional filters and pagination."""
    query = db.query(ActionItem).filter(
        ActionItem.user_id == current_user.id
    )

    if status_filter:
        query = query.filter(ActionItem.status == status_filter)
    if source:
        query = query.filter(ActionItem.source == source)
    if priority:
        query = query.filter(ActionItem.priority == priority)

    items = (
        query.order_by(ActionItem.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items


@router.post(
    "",
    response_model=ActionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_action_item(
    item_data: ActionItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemResponse:
    """Manually create an action item.

    Per spec: user can add items directly, not solely AI-dependent.
    """
    action_item = ActionItem(
        user_id=current_user.id,
        source=item_data.source.value,
        source_id=item_data.source_id,
        source_url=item_data.source_url,
        title=item_data.title,
        description=item_data.description,
        extracted_deadline=item_data.extracted_deadline,
        confidence_score=item_data.confidence_score,
        priority=item_data.priority.value,
        status=ActionItemStatus.NEW.value,
        dedup_hash=item_data.dedup_hash,
    )
    db.add(action_item)
    db.commit()
    db.refresh(action_item)
    return action_item


@router.get("/{item_id}", response_model=ActionItemResponse)
def get_action_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemResponse:
    """Get a single action item by ID."""
    item = _get_user_item(db, item_id, current_user.id)
    return item


@router.put("/{item_id}", response_model=ActionItemResponse)
def update_action_item(
    item_id: str,
    updates: ActionItemSnooze,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemResponse:
    """Update an action item (e.g., snooze)."""
    item = _get_user_item(db, item_id, current_user.id)
    item.snoozed_until = updates.snoozed_until
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/{item_id}/dismiss",
    response_model=ActionItemResponse,
)
def dismiss_item(
    item_id: str,
    dismiss_data: ActionItemDismiss,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemResponse:
    """Dismiss an action item with a reason.

    Per spec: dismissal patterns are tracked for prompt refinement.
    """
    try:
        item = dismiss_action_item(
            db, item_id, current_user.id, dismiss_data.reason
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action item not found",
        )
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/{item_id}/acknowledge",
    response_model=ActionItemResponse,
)
def acknowledge_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemResponse:
    """Mark an action item as acknowledged."""
    item = _get_user_item(db, item_id, current_user.id)
    item.status = ActionItemStatus.ACKNOWLEDGED.value
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/{item_id}/action",
    response_model=ActionItemResponse,
)
def action_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemResponse:
    """Mark an action item as actioned (done)."""
    item = _get_user_item(db, item_id, current_user.id)
    item.status = ActionItemStatus.ACTIONED.value
    item.actioned_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(item)
    return item


@router.get("/stats/dismissals")
def dismissal_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Get dismissal statistics for prompt refinement."""
    return get_dismissal_stats(db, current_user.id)


# --- Helpers ---


def _get_user_item(
    db: Session, item_id: str, user_id: str
) -> ActionItem:
    """Fetch an action item owned by the user, or raise 404."""
    item = (
        db.query(ActionItem)
        .filter(
            ActionItem.id == item_id,
            ActionItem.user_id == user_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action item not found",
        )
    return item
