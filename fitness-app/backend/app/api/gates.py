"""
PR Gate API endpoints (ARISE v2 spec §6.5).

Spawn is server-driven only — no force-spawn endpoints in prod. GET /gates
doubles as the lazy stand-in for the spec's nightly job: it expires overdue
gates and evaluates spawn rules before answering.
"""
import asyncio
import logging
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.utils import to_iso8601_utc
from app.models.exercise import Exercise
from app.models.gate import GateStatus, PRGate
from app.models.user import User
from app.schemas.gate import GateResponse
from app.services.gate_service import (
    evaluate_gate_spawns,
    get_gate_history,
    get_live_gates,
)
from app.services.notification_service import notify_gate_opened

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_response(db: Session, gate: PRGate) -> GateResponse:
    exercise = db.query(Exercise).filter(Exercise.id == gate.exercise_id).first()
    return GateResponse(
        id=gate.id,
        exercise_id=gate.exercise_id,
        exercise_name=exercise.name if exercise else "Unknown",
        rank=gate.rank,
        name=gate.name,
        target_weight=gate.target_weight,
        target_reps=gate.target_reps,
        target_e1rm=gate.target_e1rm,
        baseline_e1rm=gate.baseline_e1rm,
        projected_e1rm=gate.projected_e1rm,
        weekly_slope=gate.weekly_slope,
        condition_at_spawn=gate.condition_at_spawn,
        status=gate.status,
        spawned_at=to_iso8601_utc(gate.spawned_at),
        expires_at=to_iso8601_utc(gate.expires_at),
        accepted_at=to_iso8601_utc(gate.accepted_at) if gate.accepted_at else None,
        cleared_at=to_iso8601_utc(gate.cleared_at) if gate.cleared_at else None,
        cleared_by_set_id=gate.cleared_by_set_id,
        xp_awarded=gate.xp_awarded,
    )


@router.get("", response_model=List[GateResponse])
async def list_gates(
    client_date: Optional[str] = Query(
        None,
        description=(
            "Client's local date (YYYY-MM-DD) so the spawn rules read Condition "
            "for the user's day, not the server's UTC day (v2.1, QA W2)"
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Open/active gates. Expires overdue gates and runs the spawn rules first
    (the lazy nightly-job stand-in), so the Status tab always sees a current
    lifecycle.
    """
    parsed_date: Optional[date] = None
    if client_date:
        try:
            parsed_date = date.fromisoformat(client_date)
        except ValueError:
            logger.warning(
                "Malformed client_date %r on GET /gates — using the server day",
                client_date,
            )

    newly_spawned = evaluate_gate_spawns(db, current_user.id, client_date=parsed_date)
    for gate in newly_spawned:
        asyncio.ensure_future(notify_gate_opened(db, current_user.id, gate))

    return [_to_response(db, g) for g in get_live_gates(db, current_user.id)]


@router.post("/{gate_id}/accept", response_model=GateResponse)
async def accept_gate(
    gate_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ACCEPT GATE — a commitment marker only (spec §6.4); no mechanical change."""
    gate = (
        db.query(PRGate)
        .filter(PRGate.id == gate_id, PRGate.user_id == current_user.id)
        .first()
    )
    if gate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gate not found")
    if gate.status != GateStatus.OPEN.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Gate is {gate.status}, only open gates can be accepted",
        )

    gate.status = GateStatus.ACTIVE.value
    gate.accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(gate)
    return _to_response(db, gate)


@router.get("/history", response_model=List[GateResponse])
async def gate_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cleared/expired gates, newest first."""
    return [_to_response(db, g) for g in get_gate_history(db, current_user.id, limit)]
