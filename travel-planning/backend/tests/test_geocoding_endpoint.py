"""Tests for the geocoding API endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_geocode_success(client, test_user) -> None:
    """POST /api/v1/geocode with valid address returns coordinates."""
    mock_result = {"lat": 37.8199, "lng": -122.4783}

    with patch(
        "app.api.geocoding._get_mapkit_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.geocode.return_value = mock_result
        mock_client.client = AsyncMock()
        mock_get_client.return_value = mock_client

        resp = await client.post(
            "/api/v1/geocode",
            json={"address": "Golden Gate Bridge, San Francisco"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["lat"] == 37.8199
    assert data["lng"] == -122.4783
    assert data["address"] == "Golden Gate Bridge, San Francisco"


@pytest.mark.asyncio
async def test_geocode_not_found(client, test_user) -> None:
    """POST /api/v1/geocode with unknown address returns 404."""
    with patch(
        "app.api.geocoding._get_mapkit_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.geocode.return_value = None
        mock_client.client = AsyncMock()
        mock_get_client.return_value = mock_client

        resp = await client.post(
            "/api/v1/geocode",
            json={"address": "xyznonexistentplace12345"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_geocode_no_auth(unauth_client) -> None:
    """POST /api/v1/geocode without auth returns 401."""
    resp = await unauth_client.post(
        "/api/v1/geocode",
        json={"address": "San Francisco"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_geocode_empty_address(client, test_user) -> None:
    """POST /api/v1/geocode with empty address returns 422."""
    resp = await client.post(
        "/api/v1/geocode",
        json={"address": ""},
    )
    assert resp.status_code == 422
