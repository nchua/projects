"""
Activity/Health data API endpoints for Apple HealthKit sync
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import date

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.utils import to_iso8601_utc
from app.models.user import User
from app.models.activity import DailyActivity
from app.schemas.activity import (
    ActivityCreate,
    ActivityResponse,
    ActivityHistoryResponse,
    LastSyncResponse,
    ActivitySource
)

router = APIRouter()


def activity_to_response(entry: DailyActivity) -> ActivityResponse:
    """Convert DailyActivity model to response schema"""
    return ActivityResponse(
        id=entry.id,
        user_id=entry.user_id,
        date=to_iso8601_utc(entry.date),
        source=entry.source,
        steps=entry.steps,
        active_calories=entry.active_calories,
        total_calories=entry.total_calories,
        active_minutes=entry.active_minutes,
        exercise_minutes=entry.exercise_minutes,
        stand_hours=entry.stand_hours,
        move_calories=entry.move_calories,
        strain=entry.strain,
        recovery_score=entry.recovery_score,
        hrv=entry.hrv,
        resting_heart_rate=entry.resting_heart_rate,
        sleep_hours=entry.sleep_hours,
        created_at=to_iso8601_utc(entry.created_at),
        updated_at=to_iso8601_utc(entry.updated_at)
    )


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def sync_activity(
    data: ActivityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sync daily activity data from HealthKit (upsert - updates if entry exists for date+source)

    Args:
        data: Activity data from HealthKit
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Created or updated activity entry
    """
    # Check if entry exists for this date+source (upsert behavior)
    existing_entry = db.query(DailyActivity).filter(
        DailyActivity.user_id == current_user.id,
        DailyActivity.date == data.date,
        DailyActivity.source == data.source.value
    ).first()

    if existing_entry:
        # Update existing entry with new values
        for field, value in data.model_dump(exclude_unset=True, exclude={'date', 'source'}).items():
            if value is not None:
                setattr(existing_entry, field, value)
        db.commit()
        db.refresh(existing_entry)
        return activity_to_response(existing_entry)
    else:
        # Create new entry
        entry = DailyActivity(
            user_id=current_user.id,
            date=data.date,
            source=data.source.value,
            steps=data.steps,
            active_calories=data.active_calories,
            total_calories=data.total_calories,
            active_minutes=data.active_minutes,
            exercise_minutes=data.exercise_minutes,
            stand_hours=data.stand_hours,
            move_calories=data.move_calories,
            strain=data.strain,
            recovery_score=data.recovery_score,
            hrv=data.hrv,
            resting_heart_rate=data.resting_heart_rate,
            sleep_hours=data.sleep_hours
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return activity_to_response(entry)


@router.post("/bulk", response_model=List[ActivityResponse], status_code=status.HTTP_201_CREATED)
async def sync_activity_bulk(
    activities: List[ActivityCreate],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk sync multiple days of activity data.
    More efficient for initial sync or catching up after offline period.

    Args:
        activities: List of activity entries
        current_user: Currently authenticated user
        db: Database session

    Returns:
        List of created/updated activity entries
    """
    results = []

    for data in activities:
        # Check if entry exists for this date+source
        existing_entry = db.query(DailyActivity).filter(
            DailyActivity.user_id == current_user.id,
            DailyActivity.date == data.date,
            DailyActivity.source == data.source.value
        ).first()

        if existing_entry:
            # Update existing entry
            for field, value in data.model_dump(exclude_unset=True, exclude={'date', 'source'}).items():
                if value is not None:
                    setattr(existing_entry, field, value)
            results.append(existing_entry)
        else:
            # Create new entry
            entry = DailyActivity(
                user_id=current_user.id,
                date=data.date,
                source=data.source.value,
                steps=data.steps,
                active_calories=data.active_calories,
                total_calories=data.total_calories,
                active_minutes=data.active_minutes,
                exercise_minutes=data.exercise_minutes,
                stand_hours=data.stand_hours,
                move_calories=data.move_calories,
                strain=data.strain,
                recovery_score=data.recovery_score,
                hrv=data.hrv,
                resting_heart_rate=data.resting_heart_rate,
                sleep_hours=data.sleep_hours
            )
            db.add(entry)
            results.append(entry)

    db.commit()
    for r in results:
        db.refresh(r)

    return [activity_to_response(r) for r in results]


@router.get("", response_model=ActivityHistoryResponse)
@router.get("/", response_model=ActivityHistoryResponse)
async def get_activity_history(
    limit: int = Query(30, ge=1, le=365, description="Number of entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    source: Optional[str] = Query(None, description="Filter by source (apple_fitness, whoop, etc.)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get activity history with optional date range and source filter.

    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        start_date: Optional start date filter
        end_date: Optional end date filter
        source: Optional source filter
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Activity history with pagination info
    """
    query = db.query(DailyActivity).filter(
        DailyActivity.user_id == current_user.id
    )

    if start_date:
        query = query.filter(DailyActivity.date >= start_date)
    if end_date:
        query = query.filter(DailyActivity.date <= end_date)
    if source:
        query = query.filter(DailyActivity.source == source)

    total = query.count()
    entries = query.order_by(DailyActivity.date.desc()).offset(offset).limit(limit).all()

    return ActivityHistoryResponse(
        entries=[activity_to_response(e) for e in entries],
        total=total,
        has_more=offset + len(entries) < total
    )


@router.get("/today", response_model=Optional[ActivityResponse])
async def get_today_activity(
    source: str = Query("apple_fitness", description="Source to filter by"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get today's activity summary for a specific source.

    Args:
        source: Activity source to filter by
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Today's activity entry or null
    """
    today = date.today()
    entry = db.query(DailyActivity).filter(
        DailyActivity.user_id == current_user.id,
        DailyActivity.date == today,
        DailyActivity.source == source
    ).first()

    if not entry:
        return None

    return activity_to_response(entry)


@router.get("/last-sync", response_model=LastSyncResponse)
async def get_last_sync(
    source: str = Query("apple_fitness", description="Source to check last sync for"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the last sync date for a given source.
    Used by iOS app to determine what data needs syncing.

    Args:
        source: Activity source to check
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Last synced date and source
    """
    latest = db.query(DailyActivity).filter(
        DailyActivity.user_id == current_user.id,
        DailyActivity.source == source
    ).order_by(DailyActivity.date.desc()).first()

    return LastSyncResponse(
        last_synced_date=to_iso8601_utc(latest.date) if latest else None,
        source=source
    )


@router.get("/{entry_id}", response_model=ActivityResponse)
async def get_activity_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific activity entry by ID.

    Args:
        entry_id: Activity entry ID
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Activity entry

    Raises:
        HTTPException: If entry not found
    """
    entry = db.query(DailyActivity).filter(
        DailyActivity.id == entry_id,
        DailyActivity.user_id == current_user.id
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity entry not found"
        )

    return activity_to_response(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an activity entry.

    Args:
        entry_id: Activity entry ID
        current_user: Currently authenticated user
        db: Database session

    Raises:
        HTTPException: If entry not found
    """
    entry = db.query(DailyActivity).filter(
        DailyActivity.id == entry_id,
        DailyActivity.user_id == current_user.id
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity entry not found"
        )

    db.delete(entry)
    db.commit()

    return None
