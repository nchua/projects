"""Integration tests for auth endpoints at /api/v1/auth/."""

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from app.core.database import get_db


def _make_auth_client(db_session):
    """Return a client with only get_db overridden (real auth logic runs)."""

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

VALID_USER = {
    "email": "newuser@example.com",
    "password": "TestPass123!",
    "display_name": "Test User",
}


@pytest.mark.asyncio
async def test_register_success(db_session):
    """Register a new user and verify 201 with tokens."""
    async with _make_auth_client(db_session) as client:
        resp = await client.post(REGISTER_URL, json=VALID_USER)

    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == VALID_USER["email"]


@pytest.mark.asyncio
async def test_register_duplicate_email(db_session):
    """Registering the same email twice returns 409 EMAIL_EXISTS."""
    async with _make_auth_client(db_session) as client:
        resp1 = await client.post(REGISTER_URL, json=VALID_USER)
        assert resp1.status_code == 201

        resp2 = await client.post(REGISTER_URL, json=VALID_USER)

    assert resp2.status_code == 409
    assert resp2.headers.get("X-Error-Code") == "EMAIL_EXISTS"


@pytest.mark.asyncio
async def test_login_success(db_session):
    """Register then login with correct credentials returns 200 with token."""
    async with _make_auth_client(db_session) as client:
        await client.post(REGISTER_URL, json=VALID_USER)

        resp = await client.post(
            LOGIN_URL,
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == VALID_USER["email"]


@pytest.mark.asyncio
async def test_login_wrong_password(db_session):
    """Login with wrong password returns 401 INVALID_CREDENTIALS."""
    async with _make_auth_client(db_session) as client:
        await client.post(REGISTER_URL, json=VALID_USER)

        resp = await client.post(
            LOGIN_URL,
            json={"email": VALID_USER["email"], "password": "WrongPassword999!"},
        )

    assert resp.status_code == 401
    assert resp.headers.get("X-Error-Code") == "INVALID_CREDENTIALS"
