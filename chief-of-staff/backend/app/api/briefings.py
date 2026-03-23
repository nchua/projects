"""Briefing API endpoints."""

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.briefing import Briefing
from app.models.user import User
from app.schemas.briefing import BriefingResponse
from app.services.briefing_service import generate_morning_briefing


def _user_today(user: User) -> date:
    """Get today's date in the user's timezone."""
    now_utc = datetime.now(tz=timezone.utc)
    if user.timezone:
        try:
            from zoneinfo import ZoneInfo
            return now_utc.astimezone(
                ZoneInfo(user.timezone)
            ).date()
        except (KeyError, ImportError):
            pass
    return now_utc.date()

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/today", response_model=BriefingResponse)
def get_today_briefing(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefingResponse:
    """Get today's briefing, generating it if it doesn't exist."""
    briefing = generate_morning_briefing(
        current_user.id, db
    )
    db.commit()
    return briefing


@router.get("/{briefing_date}", response_model=BriefingResponse)
def get_briefing_by_date(
    briefing_date: date,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefingResponse:
    """Get a briefing for a specific date."""
    briefing = (
        db.query(Briefing)
        .filter(
            Briefing.user_id == current_user.id,
            Briefing.date == briefing_date,
        )
        .first()
    )
    if not briefing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No briefing found for this date",
        )
    return briefing


@router.post("/today/viewed", response_model=BriefingResponse)
def mark_briefing_viewed(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefingResponse:
    """Mark today's briefing as viewed."""
    today = _user_today(current_user)
    briefing = (
        db.query(Briefing)
        .filter(
            Briefing.user_id == current_user.id,
            Briefing.date == today,
        )
        .first()
    )
    if not briefing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No briefing found for today",
        )

    briefing.viewed_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(briefing)
    return briefing


@router.post("/preview", response_model=BriefingResponse)
def generate_preview_briefing(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefingResponse:
    """Generate a preview briefing for onboarding.

    Always generates fresh, even if one already exists.
    """
    today = _user_today(current_user)

    # Delete existing briefing for today to force regeneration
    existing = (
        db.query(Briefing)
        .filter(
            Briefing.user_id == current_user.id,
            Briefing.date == today,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        db.flush()

    briefing = generate_morning_briefing(
        current_user.id, db, target_date=today
    )
    db.commit()
    return briefing
