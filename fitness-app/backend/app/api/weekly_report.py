"""
Weekly Progress Report API endpoint
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.weekly_report import WeeklyProgressReportResponse
from app.services.weekly_report_service import generate_weekly_report
from app.services.notification_service import notify_weekly_report_ready

router = APIRouter()


@router.get("/weekly-report", response_model=WeeklyProgressReportResponse)
async def get_weekly_progress_report(
    week_start: Optional[str] = Query(
        None,
        description="Start of week (YYYY-MM-DD). Defaults to last completed week.",
    ),
    client_date: Optional[str] = Query(
        None,
        description="Client's local date (YYYY-MM-DD) to avoid timezone mismatch",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a weekly progress report with goal tracking, pace prediction,
    and actionable coaching suggestions. Defaults to the most recently
    completed week (last Monday–Sunday).
    """
    parsed_start: Optional[date] = None
    if week_start:
        parsed_start = date.fromisoformat(week_start)

    parsed_client_date: Optional[date] = None
    if client_date:
        try:
            parsed_client_date = date.fromisoformat(client_date)
        except ValueError:
            pass

    report = generate_weekly_report(db, current_user.id, parsed_start, parsed_client_date)

    # Notify user that weekly report is ready (fire-and-forget)
    import asyncio
    asyncio.ensure_future(notify_weekly_report_ready(db, current_user.id))

    return report
