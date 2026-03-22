"""P1 tests for trip lifecycle / status transitions."""

from __future__ import annotations

import pytest

from app.models.enums import TripStatus


@pytest.mark.asyncio
async def test_monitoring_to_departed(client, test_user, make_trip) -> None:
    """A monitoring trip can be transitioned to departed."""
    trip = await make_trip(status=TripStatus.monitoring)
    resp = await client.put(
        f"/api/v1/trips/{trip.id}",
        json={"status": "departed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "departed"


@pytest.mark.asyncio
async def test_completed_is_immutable(client, test_user, make_trip) -> None:
    """A completed trip cannot be updated."""
    trip = await make_trip(status=TripStatus.completed)
    resp = await client.put(
        f"/api/v1/trips/{trip.id}",
        json={"status": "cancelled"},
    )
    assert resp.status_code == 400
