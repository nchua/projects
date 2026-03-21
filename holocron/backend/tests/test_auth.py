"""Tests for authentication endpoints."""


def test_register(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "TestPass123!",
            "display_name": "New User",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_email(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "TestPass123!",
        },
    )
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 400


def test_login(client, auth_headers):
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client, auth_headers):
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPass!",
        },
    )
    assert resp.status_code == 401


def test_me(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


def test_me_no_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
