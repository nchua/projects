"""
Bodyweight tracking API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, timedelta
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.utils import to_iso8601_utc
from app.models.user import User, UserProfile, WeightUnit as ModelWeightUnit
from app.models.bodyweight import BodyweightEntry
from app.schemas.bodyweight import (
    BodyweightCreate, BodyweightResponse, BodyweightHistoryResponse,
    BodyweightTrend, WeightUnit
)

router = APIRouter()

# Conversion constants
LB_TO_KG = 0.453592
KG_TO_LB = 2.20462


def convert_to_lb(weight: float, unit: WeightUnit) -> float:
    """Convert weight to pounds for storage"""
    if unit == WeightUnit.KG:
        return weight * KG_TO_LB
    return weight


def convert_from_lb(weight_lb: float, unit: str) -> float:
    """Convert weight from pounds to display unit"""
    if unit == "kg":
        return weight_lb * LB_TO_KG
    return weight_lb


def get_user_weight_unit(user_id: str, db: Session) -> str:
    """Get user's preferred weight unit"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile and profile.preferred_unit:
        return profile.preferred_unit.value
    return "lb"


@router.post("", response_model=BodyweightResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=BodyweightResponse, status_code=status.HTTP_201_CREATED)
async def log_bodyweight(
    data: BodyweightCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Log a bodyweight entry (upsert - updates if entry exists for date)

    Args:
        data: Bodyweight entry data
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Created or updated bodyweight entry
    """
    # Convert to pounds for storage
    weight_lb = convert_to_lb(data.weight, data.weight_unit)

    # Check if entry exists for this date (upsert behavior)
    existing_entry = db.query(BodyweightEntry).filter(
        BodyweightEntry.user_id == current_user.id,
        BodyweightEntry.date == data.date
    ).first()

    if existing_entry:
        # Update existing entry
        existing_entry.weight_lb = weight_lb
        existing_entry.source = data.source
        db.commit()
        db.refresh(existing_entry)
        entry = existing_entry
    else:
        # Create new entry
        entry = BodyweightEntry(
            user_id=current_user.id,
            date=data.date,
            weight_lb=weight_lb,
            source=data.source
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

    # Get user's preferred unit for display
    display_unit = get_user_weight_unit(current_user.id, db)

    return BodyweightResponse(
        id=entry.id,
        user_id=entry.user_id,
        date=to_iso8601_utc(entry.date),
        weight_lb=round(entry.weight_lb, 2),
        weight_display=round(convert_from_lb(entry.weight_lb, display_unit), 2),
        weight_unit=display_unit,
        source=entry.source,
        created_at=to_iso8601_utc(entry.created_at),
        updated_at=to_iso8601_utc(entry.updated_at)
    )


@router.get("", response_model=BodyweightHistoryResponse)
@router.get("/", response_model=BodyweightHistoryResponse)
async def get_bodyweight_history(
    limit: int = Query(100, ge=1, le=365, description="Number of entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    start_date: Optional[date] = Query(None, description="Start date for filtering"),
    end_date: Optional[date] = Query(None, description="End date for filtering"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get bodyweight history with rolling averages and trend analysis

    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        start_date: Optional start date filter
        end_date: Optional end date filter
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Bodyweight history with analytics
    """
    # Build query
    query = db.query(BodyweightEntry).filter(
        BodyweightEntry.user_id == current_user.id
    )

    if start_date:
        query = query.filter(BodyweightEntry.date >= start_date)
    if end_date:
        query = query.filter(BodyweightEntry.date <= end_date)

    # Get total count
    total_count = query.count()

    # Get entries ordered by date descending
    entries = query.order_by(BodyweightEntry.date.desc()).limit(limit).offset(offset).all()

    # Get user's preferred unit
    display_unit = get_user_weight_unit(current_user.id, db)

    # Build response entries
    response_entries = [
        BodyweightResponse(
            id=e.id,
            user_id=e.user_id,
            date=to_iso8601_utc(e.date),
            weight_lb=round(e.weight_lb, 2),
            weight_display=round(convert_from_lb(e.weight_lb, display_unit), 2),
            weight_unit=display_unit,
            source=e.source,
            created_at=to_iso8601_utc(e.created_at),
            updated_at=to_iso8601_utc(e.updated_at)
        )
        for e in entries
    ]

    # Calculate analytics if we have enough data
    rolling_avg_7 = None
    rolling_avg_14 = None
    trend = BodyweightTrend.INSUFFICIENT_DATA
    trend_rate = None
    is_plateau = False
    min_weight = None
    max_weight = None

    if total_count > 0:
        # Get recent entries for analytics (last 14 days)
        today = date.today()
        recent_7 = db.query(BodyweightEntry).filter(
            BodyweightEntry.user_id == current_user.id,
            BodyweightEntry.date >= today - timedelta(days=7)
        ).all()

        recent_14 = db.query(BodyweightEntry).filter(
            BodyweightEntry.user_id == current_user.id,
            BodyweightEntry.date >= today - timedelta(days=14)
        ).all()

        # Calculate 7-day rolling average
        if len(recent_7) >= 3:
            rolling_avg_7 = sum(e.weight_lb for e in recent_7) / len(recent_7)
            rolling_avg_7 = round(convert_from_lb(rolling_avg_7, display_unit), 2)

        # Calculate 14-day rolling average
        if len(recent_14) >= 5:
            rolling_avg_14 = sum(e.weight_lb for e in recent_14) / len(recent_14)
            rolling_avg_14 = round(convert_from_lb(rolling_avg_14, display_unit), 2)

        # Determine trend (need at least 7 days of data)
        if len(recent_14) >= 7:
            # Sort by date ascending for trend calculation
            sorted_entries = sorted(recent_14, key=lambda e: e.date)

            # Compare first half average to second half average
            mid = len(sorted_entries) // 2
            first_half_avg = sum(e.weight_lb for e in sorted_entries[:mid]) / mid
            second_half_avg = sum(e.weight_lb for e in sorted_entries[mid:]) / len(sorted_entries[mid:])

            diff = second_half_avg - first_half_avg
            diff_percent = abs(diff / first_half_avg) * 100 if first_half_avg > 0 else 0

            # Calculate weekly rate (approximate)
            days_span = (sorted_entries[-1].date - sorted_entries[0].date).days
            if days_span > 0:
                trend_rate = (diff / days_span) * 7  # lbs per week
                trend_rate = round(convert_from_lb(trend_rate, display_unit), 2)

            # Determine trend direction
            if diff_percent < 0.5:  # Less than 0.5% change
                trend = BodyweightTrend.MAINTAINING
                # Check for plateau (stable for 14+ days)
                if len(recent_14) >= 10:
                    weights = [e.weight_lb for e in recent_14]
                    weight_std = (sum((w - (sum(weights)/len(weights)))**2 for w in weights) / len(weights)) ** 0.5
                    if weight_std < 1.0:  # Less than 1 lb standard deviation
                        is_plateau = True
            elif diff > 0:
                trend = BodyweightTrend.GAINING
            else:
                trend = BodyweightTrend.LOSING

        # Get min/max from all entries
        all_weights = db.query(
            func.min(BodyweightEntry.weight_lb),
            func.max(BodyweightEntry.weight_lb)
        ).filter(BodyweightEntry.user_id == current_user.id).first()

        if all_weights[0] is not None:
            min_weight = round(convert_from_lb(all_weights[0], display_unit), 2)
            max_weight = round(convert_from_lb(all_weights[1], display_unit), 2)

    return BodyweightHistoryResponse(
        entries=response_entries,
        rolling_average_7day=rolling_avg_7,
        rolling_average_14day=rolling_avg_14,
        trend=trend,
        trend_rate_per_week=trend_rate,
        is_plateau=is_plateau,
        min_weight=min_weight,
        max_weight=max_weight,
        total_entries=total_count
    )


@router.get("/{entry_id}", response_model=BodyweightResponse)
async def get_bodyweight_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific bodyweight entry by ID

    Args:
        entry_id: Bodyweight entry ID
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Bodyweight entry

    Raises:
        HTTPException: If entry not found
    """
    entry = db.query(BodyweightEntry).filter(
        BodyweightEntry.id == entry_id,
        BodyweightEntry.user_id == current_user.id
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bodyweight entry not found"
        )

    display_unit = get_user_weight_unit(current_user.id, db)

    return BodyweightResponse(
        id=entry.id,
        user_id=entry.user_id,
        date=to_iso8601_utc(entry.date),
        weight_lb=round(entry.weight_lb, 2),
        weight_display=round(convert_from_lb(entry.weight_lb, display_unit), 2),
        weight_unit=display_unit,
        source=entry.source,
        created_at=to_iso8601_utc(entry.created_at),
        updated_at=to_iso8601_utc(entry.updated_at)
    )


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bodyweight_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a bodyweight entry

    Args:
        entry_id: Bodyweight entry ID
        current_user: Currently authenticated user
        db: Database session

    Raises:
        HTTPException: If entry not found
    """
    entry = db.query(BodyweightEntry).filter(
        BodyweightEntry.id == entry_id,
        BodyweightEntry.user_id == current_user.id
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bodyweight entry not found"
        )

    db.delete(entry)
    db.commit()

    return None
