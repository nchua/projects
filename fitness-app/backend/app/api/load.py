"""
Training load API (ARISE v3 spec §6.2 / §15.4).

``GET /load`` is the Status LOAD strip's read: the 28-day run acute/chronic
series, the ACWR band, ``miles_7d`` vs the plan, and the guard flags for the
client's local day. Reading it also refreshes the daily series when a session
landed since the last recompute (the lazy stand-in for a scheduler).
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.load import LoadSeriesPoint, TrainingLoadResponse
from app.services.training_load_service import get_load_state

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=TrainingLoadResponse)
async def get_load(
    client_date: Optional[str] = Query(
        None,
        description="Client's local date (YYYY-MM-DD); the series ends on this day",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Training-load state for the user's local day (spec §15.4)."""
    as_of = date.today()
    if client_date:
        try:
            as_of = date.fromisoformat(client_date)
        except ValueError:
            logger.warning(
                "Malformed client_date %r on GET /load — using the server day", client_date
            )

    state = get_load_state(db, current_user.id, as_of)
    return TrainingLoadResponse(
        as_of=state["as_of"],
        run_acute_7d=state["run_acute_7d"],
        run_chronic_28d=state["run_chronic_28d"],
        run_acwr=state["run_acwr"],
        band=state["band"],
        miles_7d=state["miles_7d"],
        miles_plan_7d=state["miles_plan_7d"],
        longest_run_7d=state["longest_run_7d"],
        flags=state["flags"],
        series=[LoadSeriesPoint(**point) for point in state["series"]],
    )
