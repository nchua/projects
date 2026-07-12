"""
System Directive API endpoints (ARISE v2 spec §5.3).
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.utils import to_iso8601_utc
from app.models.directive import UserDirective
from app.models.user import User, UserProfile
from app.schemas.directive import DirectiveHistoryResponse, DirectiveResponse
from app.services.directive_service import (
    get_directive_history,
    get_or_generate_directive,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_response(directive: UserDirective) -> DirectiveResponse:
    return DirectiveResponse(
        id=directive.id,
        date=directive.date.isoformat(),
        directive_type=directive.directive_type,
        message=directive.message,
        params=directive.params,
        xp_reward=directive.xp_reward,
        is_completed=directive.is_completed,
        completed_at=(
            to_iso8601_utc(directive.completed_at) if directive.completed_at else None
        ),
    )


@router.get("/today", response_model=DirectiveResponse)
async def get_today_directive(
    client_date: Optional[str] = Query(
        None,
        description="Client's local date (YYYY-MM-DD) to avoid timezone mismatch",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return today's System Directive, generating it on first call of the
    user's local day (deterministic for the day — persisted row).
    """
    parsed_date: Optional[date] = None
    if client_date:
        try:
            parsed_date = date.fromisoformat(client_date)
        except ValueError:
            logger.warning(
                "Malformed client_date %r on GET /directive/today — using the server day",
                client_date,
            )

    profile = db.query(UserProfile).filter(
        UserProfile.user_id == current_user.id
    ).first()
    user_age = profile.age if profile else None

    directive = get_or_generate_directive(db, current_user.id, parsed_date, user_age)
    return _to_response(directive)


@router.get("/history", response_model=DirectiveHistoryResponse)
async def get_history(
    limit: int = Query(7, ge=1, le=60),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent directives, newest first (for the Directive sheet)."""
    directives = get_directive_history(db, current_user.id, limit)
    return DirectiveHistoryResponse(
        directives=[_to_response(d) for d in directives]
    )
