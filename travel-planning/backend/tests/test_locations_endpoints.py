"""P1 tests for saved locations API endpoints."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# POST /locations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_location_success(client, test_user) -> None:
    """POST /api/v1/locations with valid data returns 201."""
    resp = await client.post(
        "/api/v1/locations",
        json={
            "name": "Home",
            "address": "123 Main St, San Francisco, CA",
            "latitude": 37.7749,
            "longitude": -122.4194,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Home"
    assert data["latitude"] == 37.7749


@pytest.mark.asyncio
async def test_create_location_duplicate_name(client, test_user) -> None:
    """Creating two locations with the same name returns 409."""
    payload = {
        "name": "Work",
        "address": "456 Office Ave",
        "latitude": 37.3382,
        "longitude": -121.8863,
    }
    resp1 = await client.post("/api/v1/locations", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/locations", json=payload)
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# GET /locations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_locations(client, test_user) -> None:
    """GET /api/v1/locations returns all user locations."""
    await client.post(
        "/api/v1/locations",
        json={
            "name": "Home",
            "address": "123 Main St",
            "latitude": 37.7749,
            "longitude": -122.4194,
        },
    )
    resp = await client.get("/api/v1/locations")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# DELETE /locations/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_location(client, test_user) -> None:
    """DELETE /api/v1/locations/{id} soft-deletes and returns 204."""
    create_resp = await client.post(
        "/api/v1/locations",
        json={
            "name": "Gym",
            "address": "789 Fitness Blvd",
            "latitude": 37.78,
            "longitude": -122.41,
        },
    )
    loc_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/locations/{loc_id}")
    assert del_resp.status_code == 204

    # Verify it's gone from the list
    list_resp = await client.get("/api/v1/locations")
    assert len(list_resp.json()) == 0
