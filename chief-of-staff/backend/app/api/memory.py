"""Memory API endpoints — transparency + manual control."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.memory_fact import MemoryFact
from app.models.user import User
from app.schemas.memory_fact import MemoryFactCreate, MemoryFactResponse
from app.services.memory_service import persist_memory_facts

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[MemoryFactResponse])
def list_memory_facts(
    active_only: bool = Query(True, description="Only show active facts"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemoryFactResponse]:
    """List memory facts for transparency.

    Users can see what the system remembers about their context.
    """
    query = db.query(MemoryFact).filter(
        MemoryFact.user_id == current_user.id
    )

    if active_only:
        query = query.filter(MemoryFact.is_active.is_(True))

    facts = (
        query.order_by(MemoryFact.importance.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return facts


@router.post(
    "",
    response_model=MemoryFactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_memory_fact(
    data: MemoryFactCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemoryFactResponse:
    """Manually add a memory fact.

    Example: "Remember: Q3 planning is July 15"
    """
    now = datetime.now(tz=timezone.utc)

    facts = persist_memory_facts(
        [
            {
                "fact_text": data.fact_text,
                "fact_type": data.fact_type,
                "people": data.people,
                "valid_from": (
                    data.valid_from.isoformat() if data.valid_from else None
                ),
                "valid_until": (
                    data.valid_until.isoformat() if data.valid_until else None
                ),
                "importance": data.importance,
                "confidence": 1.0,  # Manual facts are high confidence
                "source": "manual",
            }
        ],
        current_user.id,
        db,
    )

    if not facts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create memory fact (possible duplicate)",
        )

    db.commit()
    db.refresh(facts[0])
    return facts[0]


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory_fact(
    fact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a memory fact (mark as inactive)."""
    fact = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.id == fact_id,
            MemoryFact.user_id == current_user.id,
        )
        .first()
    )
    if not fact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory fact not found",
        )

    fact.is_active = False
    fact.invalidated_at = datetime.now(tz=timezone.utc)
    db.commit()
