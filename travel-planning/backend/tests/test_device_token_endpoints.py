"""P1 tests for device token API endpoints."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# POST /device-tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_device_token(client, test_user) -> None:
    """POST /api/v1/device-tokens registers a new APNs device token."""
    resp = await client.post(
        "/api/v1/device-tokens",
        json={"token": "fake-device-token-for-testing", "platform": "ios"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["token"] == "fake-device-token-for-testing"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_device_token_upsert(client, test_user) -> None:
    """Registering the same token twice upserts (no duplicate error)."""
    payload = {"token": "apns-token-upsert", "platform": "ios"}
    resp1 = await client.post("/api/v1/device-tokens", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/device-tokens", json=payload)
    assert resp2.status_code in (200, 201)


# ---------------------------------------------------------------------------
# DELETE /device-tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_device_token(client, test_user) -> None:
    """DELETE /api/v1/device-tokens deactivates a token."""
    # Register first
    await client.post(
        "/api/v1/device-tokens",
        json={"token": "apns-token-to-delete", "platform": "ios"},
    )

    # Delete
    resp = await client.request(
        "DELETE",
        "/api/v1/device-tokens",
        json={"token": "apns-token-to-delete"},
    )
    assert resp.status_code == 204
