"""Integration tests for trip endpoints at /api/v1/trips/."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.enums import TripStatus


TRIPS_URL = "/api/v1/trips"


def _future_iso(hours: int = 2) -> str:
    """Return an ISO-formatted UTC datetime `hours` in the future."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _valid_trip_body(**overrides) -> dict:
    """Return a minimal valid CreateTripRequest body."""
    body = {
        "name": "Airport Run",
        "dest_address": "SFO Airport",
        "dest_lat": 37.6213,
        "dest_lng": -122.3790,
        "arrival_time": _future_iso(2),
        "origin_is_current_location": True,
        "buffer_minutes": 15,
    }
    body.update(overrides)
    return body


# ── Create ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_trip_success(client):
    """POST a valid trip returns 201 with pending status and notify_at."""
    resp = await client.post(TRIPS_URL, json=_valid_trip_body())

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["name"] == "Airport Run"
    assert "notify_at" in data


@pytest.mark.asyncio
async def test_create_trip_no_auth(unauth_client):
    """POST without auth returns 401."""
    resp = await unauth_client.post(TRIPS_URL, json=_valid_trip_body())

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_trip_past_arrival(client):
    """POST with arrival_time in the past returns 422."""
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    resp = await client.post(TRIPS_URL, json=_valid_trip_body(arrival_time=past))

    assert resp.status_code == 422


# ── Read ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_trip_detail(client, make_trip):
    """GET /{id} returns 200 with eta_snapshots list."""
    trip = await make_trip(
        name="Detail Trip",
        arrival_hours_from_now=3,
        buffer_minutes=10,
        status=TripStatus.pending,
    )

    resp = await client.get(f"{TRIPS_URL}/{trip.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Trip"
    assert "eta_snapshots" in data
    assert isinstance(data["eta_snapshots"], list)


@pytest.mark.asyncio
async def test_get_trip_other_user(client, make_trip, second_user, db_session):
    """GET a trip owned by test_user as second_user returns 404."""
    trip = await make_trip(
        name="Private Trip",
        arrival_hours_from_now=3,
        buffer_minutes=10,
        status=TripStatus.pending,
    )

    # Build a client authenticated as the second user
    async def _db_gen():
        yield db_session

    app.dependency_overrides[get_db] = _db_gen
    app.dependency_overrides[get_current_user] = lambda: second_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as other_client:
        resp = await other_client.get(f"{TRIPS_URL}/{trip.id}")

    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_trip_status_cancelled(client, make_trip):
    """PUT status=cancelled on a pending trip returns 200."""
    trip = await make_trip(
        name="Cancel Me",
        arrival_hours_from_now=4,
        buffer_minutes=10,
        status=TripStatus.pending,
    )

    resp = await client.put(
        f"{TRIPS_URL}/{trip.id}",
        json={"status": "cancelled"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_update_trip_immutable_status(client, make_trip):
    """PUT on a departed trip returns 400 (immutable status)."""
    trip = await make_trip(
        name="Already Left",
        arrival_hours_from_now=1,
        buffer_minutes=5,
        status=TripStatus.departed,
    )

    resp = await client.put(
        f"{TRIPS_URL}/{trip.id}",
        json={"name": "Renamed"},
    )

    assert resp.status_code == 400


# ── Delete ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_trip_soft_delete(client, make_trip):
    """DELETE returns 204 and the trip is no longer retrievable."""
    trip = await make_trip(
        name="Delete Me",
        arrival_hours_from_now=5,
        buffer_minutes=10,
        status=TripStatus.pending,
    )

    resp = await client.delete(f"{TRIPS_URL}/{trip.id}")
    assert resp.status_code == 204

    # Confirm the trip is gone from the user's perspective
    get_resp = await client.get(f"{TRIPS_URL}/{trip.id}")
    assert get_resp.status_code == 404
