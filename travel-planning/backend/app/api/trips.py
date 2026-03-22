"""Trip CRUD, listing, filtering, and detail endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from zoneinfo import ZoneInfo

from app.api.deps import get_current_user, get_db
from app.models.enums import TravelMode, TripStatus
from app.models.saved_location import SavedLocation
from app.models.trip import Trip
from app.models.user import User
from app.schemas.trip import (
    CreateTripRequest,
    EtaSnapshotResponse,
    NotificationResponse,
    PaginatedTripResponse,
    TripDetailResponse,
    TripResponse,
    UpdateTripRequest,
)

router = APIRouter(prefix="/trips", tags=["trips"])

# Status transitions allowed from the client side
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"cancelled"},
    "monitoring": {"cancelled", "departed"},
    "notified": {"cancelled", "departed"},
}

# Statuses that block any modification
_IMMUTABLE_STATUSES = {"departed", "completed", "cancelled"}


async def _verify_location_ownership(
    db: AsyncSession,
    location_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> None:
    """Verify a saved location exists and belongs to the user."""
    if location_id is None:
        return
    result = await db.execute(
        select(SavedLocation).where(
            SavedLocation.id == location_id,
            SavedLocation.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved location not found",
            headers={"X-Error-Code": "LOCATION_NOT_FOUND"},
        )


async def _get_user_trip(
    db: AsyncSession,
    trip_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Trip:
    """Fetch a non-deleted trip owned by the user, or raise 404."""
    result = await db.execute(
        select(Trip).where(
            Trip.id == trip_id,
            Trip.user_id == user_id,
            Trip.is_deleted.is_(False),
        )
    )
    trip = result.scalar_one_or_none()
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
            headers={"X-Error-Code": "TRIP_NOT_FOUND"},
        )
    return trip


@router.post(
    "",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_trip(
    body: CreateTripRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    """Create a new trip with validation."""
    # Verify saved location ownership
    await _verify_location_ownership(db, body.origin_location_id, current_user.id)
    await _verify_location_ownership(db, body.dest_location_id, current_user.id)

    # Calendar event dedup
    if body.calendar_event_id is not None:
        result = await db.execute(
            select(Trip).where(
                Trip.user_id == current_user.id,
                Trip.calendar_event_id == body.calendar_event_id,
                Trip.is_deleted.is_(False),
            )
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Trip for this calendar event already exists",
                headers={"X-Error-Code": "CALENDAR_EVENT_DUPLICATE"},
            )

    # Resolve defaults from user preferences
    travel_mode = (
        TravelMode(body.travel_mode)
        if body.travel_mode
        else current_user.default_travel_mode
    )
    buffer_minutes = (
        body.buffer_minutes
        if body.buffer_minutes is not None
        else current_user.default_buffer_minutes
    )

    # Compute initial notify_at
    notify_at = body.arrival_time - timedelta(minutes=buffer_minutes)

    trip = Trip(
        user_id=current_user.id,
        name=body.name,
        origin_address=body.origin_address or "",
        origin_lat=body.origin_lat or 0.0,
        origin_lng=body.origin_lng or 0.0,
        origin_location_id=body.origin_location_id,
        origin_is_current_location=body.origin_is_current_location,
        dest_address=body.dest_address,
        dest_lat=body.dest_lat,
        dest_lng=body.dest_lng,
        dest_location_id=body.dest_location_id,
        arrival_time=body.arrival_time,
        travel_mode=travel_mode,
        buffer_minutes=buffer_minutes,
        status=TripStatus.pending,
        notify_at=notify_at,
        is_recurring=body.is_recurring,
        recurrence_rule=body.recurrence_rule,
        calendar_event_id=body.calendar_event_id,
    )
    db.add(trip)
    await db.flush()
    await db.refresh(trip)

    return TripResponse.model_validate(trip)


@router.get("", response_model=PaginatedTripResponse)
async def list_trips(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    trip_status: str | None = Query(None, alias="status"),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    sort_by: str = Query("arrival_time"),
    sort_order: str = Query("asc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedTripResponse:
    """List current user's trips with filtering, sorting, and pagination."""
    base_query = select(Trip).where(
        Trip.user_id == current_user.id,
        Trip.is_deleted.is_(False),
    )

    # Status filter (supports comma-separated)
    if trip_status:
        statuses = [s.strip() for s in trip_status.split(",")]
        base_query = base_query.where(Trip.status.in_(statuses))

    # Date range filters
    if from_date:
        base_query = base_query.where(Trip.arrival_time >= from_date)
    if to_date:
        base_query = base_query.where(Trip.arrival_time <= to_date)

    # Count total before pagination
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Sorting
    sort_column = Trip.arrival_time if sort_by == "arrival_time" else Trip.created_at
    if sort_order == "desc":
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    # Pagination
    base_query = base_query.offset(offset).limit(limit)

    result = await db.execute(base_query)
    trips = result.scalars().all()

    return PaginatedTripResponse(
        items=[TripResponse.model_validate(t) for t in trips],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/upcoming", response_model=list[TripResponse])
async def list_upcoming_trips(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TripResponse]:
    """Return today's and tomorrow's active trips for the dashboard."""
    tz = ZoneInfo(current_user.timezone)
    now_local = datetime.now(tz)
    start_of_today = now_local.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_tomorrow = start_of_today + timedelta(days=2)

    # Convert to UTC for DB comparison
    start_utc = start_of_today.astimezone(timezone.utc)
    end_utc = end_of_tomorrow.astimezone(timezone.utc)

    excluded_statuses = [TripStatus.completed, TripStatus.cancelled]

    result = await db.execute(
        select(Trip)
        .where(
            Trip.user_id == current_user.id,
            Trip.is_deleted.is_(False),
            Trip.status.notin_(excluded_statuses),
            Trip.arrival_time >= start_utc,
            Trip.arrival_time < end_utc,
        )
        .order_by(Trip.arrival_time.asc())
    )
    trips = result.scalars().all()

    return [TripResponse.model_validate(t) for t in trips]


@router.get("/{trip_id}", response_model=TripDetailResponse)
async def get_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TripDetailResponse:
    """Get a single trip with ETA snapshots and notification history."""
    # Load trip with relationships
    result = await db.execute(
        select(Trip)
        .options(
            selectinload(Trip.eta_snapshots),
            selectinload(Trip.notifications),
        )
        .where(
            Trip.id == trip_id,
            Trip.user_id == current_user.id,
            Trip.is_deleted.is_(False),
        )
    )
    trip = result.scalar_one_or_none()
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
            headers={"X-Error-Code": "TRIP_NOT_FOUND"},
        )

    # Build response with last 10 ETA snapshots (desc) and all notifications (desc)
    snapshots_sorted = sorted(
        trip.eta_snapshots, key=lambda s: s.checked_at, reverse=True
    )[:10]
    notifications_sorted = sorted(
        trip.notifications, key=lambda n: n.sent_at, reverse=True
    )

    response = TripDetailResponse.model_validate(trip)
    response.eta_snapshots = [
        EtaSnapshotResponse.model_validate(s) for s in snapshots_sorted
    ]
    response.notifications = [
        NotificationResponse.model_validate(n) for n in notifications_sorted
    ]
    return response


@router.put("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: uuid.UUID,
    body: UpdateTripRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    """Update a trip with ownership and status transition validation."""
    trip = await _get_user_trip(db, trip_id, current_user.id)

    # Check immutable statuses
    if trip.status.value in _IMMUTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update a {trip.status.value} trip",
            headers={"X-Error-Code": "INVALID_STATUS_TRANSITION"},
        )

    update_data = body.model_dump(exclude_unset=True)

    # Validate status transition if provided
    if "status" in update_data and update_data["status"] is not None:
        new_status = update_data["status"]
        allowed = _ALLOWED_TRANSITIONS.get(trip.status.value, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot transition from '{trip.status.value}' "
                    f"to '{new_status}'"
                ),
                headers={"X-Error-Code": "INVALID_STATUS_TRANSITION"},
            )

    # Verify location ownership if changed
    if "origin_location_id" in update_data:
        await _verify_location_ownership(
            db, update_data["origin_location_id"], current_user.id
        )
    if "dest_location_id" in update_data:
        await _verify_location_ownership(
            db, update_data["dest_location_id"], current_user.id
        )

    # Detect if route or timing changed to recalculate notify_at
    route_changed = any(
        k in update_data
        for k in (
            "origin_address", "origin_lat", "origin_lng",
            "dest_address", "dest_lat", "dest_lng",
            "arrival_time", "buffer_minutes",
        )
    )

    # Convert string values to enum types before applying
    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = TripStatus(update_data["status"])
    if "travel_mode" in update_data and update_data["travel_mode"] is not None:
        update_data["travel_mode"] = TravelMode(update_data["travel_mode"])

    # Apply updates
    for field, value in update_data.items():
        setattr(trip, field, value)

    # Recalculate notify_at if route/timing changed
    if route_changed:
        trip.last_eta_seconds = None
        buffer = trip.buffer_minutes
        trip.notify_at = trip.arrival_time - timedelta(minutes=buffer)

    await db.flush()
    await db.refresh(trip)

    return TripResponse.model_validate(trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a trip (sets is_deleted and status to cancelled)."""
    trip = await _get_user_trip(db, trip_id, current_user.id)

    trip.is_deleted = True
    trip.status = TripStatus.cancelled

    await db.flush()
