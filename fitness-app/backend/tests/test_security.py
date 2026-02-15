"""
Tests for security utilities and app-level security endpoints.

Covers: password hashing, JWT token types, privacy policy endpoint.
"""
import pytest
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
)


class TestPasswordHashing:
    """Tests for bcrypt password hashing utilities."""

    def test_hash_and_verify_password(self):
        """Round-trip: hash then verify succeeds."""
        plain = "SecurePass123!"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed)

    def test_verify_wrong_password(self):
        """Verify with wrong password returns False."""
        hashed = hash_password("CorrectPass1!")
        assert verify_password("WrongPass1!", hashed) is False


class TestJWTTokenTypes:
    """Tests for JWT token type enforcement."""

    def test_access_token_has_correct_type(self):
        """Access token payload contains type='access'."""
        token = create_access_token(data={"sub": "user-123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["type"] == "access"

    def test_refresh_token_has_correct_type(self):
        """Refresh token payload contains type='refresh'."""
        token = create_refresh_token(data={"sub": "user-123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["type"] == "refresh"

    def test_verify_token_rejects_wrong_type(self):
        """Access token verified as refresh type returns None."""
        access_token = create_access_token(data={"sub": "user-123"})
        result = verify_token(access_token, token_type="refresh")
        assert result is None


class TestPrivacyEndpoint:
    """Tests for GET /privacy."""

    def test_privacy_endpoint_returns_html(self, client):
        """Privacy page returns 200 with HTML containing 'ARISE'."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "ARISE" in response.text
