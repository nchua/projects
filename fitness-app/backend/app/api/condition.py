"""
Hunter Condition API endpoint (ARISE v2 spec §4.3).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.schemas.condition import ConditionResponse
from app.services.condition_service import compute_condition

router = APIRouter()


@router.get("", response_model=ConditionResponse)
async def get_condition(
    client_date: Optional[str] = Query(
        None,
        description="Client's local date (YYYY-MM-DD) to avoid timezone mismatch",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Compute the Hunter Condition score (0-100) on the fly.

    Five weighted inputs (WHOOP recovery, muscle freshness, sleep,
    yesterday's strain, resting-HR trend); missing inputs are dropped and
    the remaining weights renormalized, so the score never comes up empty.
    """
    parsed_date: Optional[date] = None
    if client_date:
        try:
            parsed_date = date.fromisoformat(client_date)
        except ValueError:
            pass

    profile = db.query(UserProfile).filter(
        UserProfile.user_id == current_user.id
    ).first()
    user_age = profile.age if profile else None

    return compute_condition(db, current_user.id, parsed_date, user_age)
