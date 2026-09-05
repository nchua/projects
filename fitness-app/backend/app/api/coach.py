"""
The Coach API (ARISE v3 spec §8.4, contract §15.5).

``GET /coach/debrief`` returns the weekly Debrief (generated lazily, stored
once per week); ``POST /coach/debrief/{id}/adjustments/{adj_id}`` records an
ACCEPT / DISMISS decision and, on accept, rewrites next week's planned hunts
through the campaign appliers.
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.coach import CoachOutput, CoachOutputKind
from app.models.user import User
from app.schemas.coach import AdjustmentDecisionRequest, DebriefResponse
from app.services.debrief_service import (
    AdjustmentAlreadyDecided,
    AdjustmentNotFound,
    AdjustmentOutOfBounds,
    ApplierUnavailable,
    apply_decision,
    debrief_to_response,
    default_week_start,
    get_or_create_debrief,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_date(value: Optional[str], name: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be YYYY-MM-DD")


@router.get("/debrief", response_model=DebriefResponse)
def get_debrief(
    week_start: Optional[str] = Query(
        None, description="Monday of the week (YYYY-MM-DD). Defaults to the last completed week.",
    ),
    client_date: Optional[str] = Query(
        None, description="Client's local date (YYYY-MM-DD) to avoid timezone mismatch",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The weekly Debrief. Generated on first fetch once the week has ended
    (or once Saturday's hunt is logged); before that the engine step alone
    is returned and nothing is stored."""
    parsed_client = _parse_date(client_date, "client_date")
    parsed_week = _parse_date(week_start, "week_start")
    today = parsed_client or date.today()
    target = parsed_week or default_week_start(today)
    row = get_or_create_debrief(db, current_user.id, target, client_date=parsed_client)
    return debrief_to_response(db, row, current_user.id)


@router.post("/debrief/{debrief_id}/adjustments/{adj_id}", response_model=DebriefResponse)
def decide_adjustment(
    debrief_id: str,
    adj_id: str,
    body: AdjustmentDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ACCEPT applies the op to next week's plan; DISMISS records it.
    Out-of-bounds ops are visible but can never be accepted (422)."""
    row = (
        db.query(CoachOutput)
        .filter(
            CoachOutput.id == debrief_id,
            CoachOutput.user_id == current_user.id,
            CoachOutput.kind == CoachOutputKind.DEBRIEF.value,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Debrief not found")
    try:
        row = apply_decision(db, row, adj_id, body.decision)
    except AdjustmentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except AdjustmentOutOfBounds as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AdjustmentAlreadyDecided as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ApplierUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    return debrief_to_response(db, row, current_user.id)
