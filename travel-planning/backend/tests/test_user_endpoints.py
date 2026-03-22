"""P1 tests for user profile API endpoints."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile(client, test_user) -> None:
    """GET /api/v1/users/me returns current user's profile."""
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test User"


@pytest.mark.asyncio
async def test_get_profile_no_auth(unauth_client) -> None:
    """GET /api/v1/users/me without auth returns 401."""
    resp = await unauth_client.get("/api/v1/users/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /users/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_profile(client, test_user) -> None:
    """PATCH /api/v1/users/me updates user preferences."""
    resp = await client.patch(
        "/api/v1/users/me",
        json={
            "display_name": "Updated Name",
            "default_buffer_minutes": 20,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Updated Name"
    assert data["default_buffer_minutes"] == 20
