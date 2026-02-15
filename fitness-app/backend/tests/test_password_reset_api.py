"""
Integration tests for password reset API endpoints.

Tests hit real FastAPI endpoints via TestClient with a test SQLite database.
Email sending is mocked to avoid external dependencies.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from app.models.password_reset import generate_reset_code, PasswordResetToken
from app.models.user import User
from app.core.security import hash_password, verify_password


class TestRequestPasswordReset:
    """Tests for POST /auth/password-reset/request"""

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_request_reset_returns_success_for_existing_email(self, mock_email, client, create_test_user):
        """Existing email returns 200 with generic message."""
        create_test_user(email="reset@example.com")
        response = client.post("/auth/password-reset/request", json={
            "email": "reset@example.com",
        })
        assert response.status_code == 200
        assert "reset code" in response.json()["message"].lower()

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_request_reset_returns_success_for_nonexistent_email(self, mock_email, client):
        """Non-existent email also returns 200 (anti-enumeration)."""
        response = client.post("/auth/password-reset/request", json={
            "email": "nobody@example.com",
        })
        assert response.status_code == 200

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_request_reset_rate_limited(self, mock_email, client, create_test_user):
        """Second request within cooldown is silently ignored (still 200)."""
        create_test_user(email="ratelimit@example.com")
        # First request
        client.post("/auth/password-reset/request", json={"email": "ratelimit@example.com"})
        # Second request within 2 min cooldown
        response = client.post("/auth/password-reset/request", json={"email": "ratelimit@example.com"})
        assert response.status_code == 200
        # Only one email should have been sent (first request)
        assert mock_email.call_count == 1


class TestVerifyPasswordReset:
    """Tests for POST /auth/password-reset/verify"""

    def _create_reset_token(self, db, user, code="123456", minutes_ago=0):
        """Helper to create a password reset token in the test DB."""
        token = PasswordResetToken(
            user_id=user.id,
            email=user.email,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=15) - timedelta(minutes=minutes_ago),
        )
        db.add(token)
        db.commit()
        return token

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_verify_correct_code(self, mock_email, client, db, create_test_user):
        """Correct code + new password updates the password."""
        user, _ = create_test_user(email="verify@example.com", password="OldPass123!")
        self._create_reset_token(db, user, code="654321")

        response = client.post("/auth/password-reset/verify", json={
            "email": "verify@example.com",
            "code": "654321",
            "new_password": "NewPass456!",
        })
        assert response.status_code == 200

        # Verify password was actually changed
        db.expire_all()
        updated_user = db.query(User).filter(User.id == user.id).first()
        assert verify_password("NewPass456!", updated_user.password_hash)

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_verify_wrong_code(self, mock_email, client, db, create_test_user):
        """Wrong code returns 400 with remaining attempts."""
        user, _ = create_test_user(email="wrongcode@example.com")
        self._create_reset_token(db, user, code="111111")

        response = client.post("/auth/password-reset/verify", json={
            "email": "wrongcode@example.com",
            "code": "999999",
            "new_password": "NewPass456!",
        })
        assert response.status_code == 400
        assert "attempts remaining" in response.json()["detail"].lower()

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_verify_expired_code(self, mock_email, client, db, create_test_user):
        """Token past 15 min returns 400."""
        user, _ = create_test_user(email="expired@example.com")
        # Create a token that expired 1 minute ago
        token = PasswordResetToken(
            user_id=user.id,
            email=user.email,
            code="123456",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        db.add(token)
        db.commit()

        response = client.post("/auth/password-reset/verify", json={
            "email": "expired@example.com",
            "code": "123456",
            "new_password": "NewPass456!",
        })
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_verify_max_attempts(self, mock_email, client, db, create_test_user):
        """5 wrong codes invalidates token, returns 400."""
        user, _ = create_test_user(email="maxattempts@example.com")
        token = self._create_reset_token(db, user, code="111111")
        token.attempts = 5  # Already at max
        db.commit()

        response = client.post("/auth/password-reset/verify", json={
            "email": "maxattempts@example.com",
            "code": "111111",
            "new_password": "NewPass456!",
        })
        assert response.status_code == 400
        assert "too many" in response.json()["detail"].lower()

    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_verify_deleted_user(self, mock_email, client, db, deleted_user):
        """Deleted user code returns 400."""
        self._create_reset_token(db, deleted_user, code="123456")

        response = client.post("/auth/password-reset/verify", json={
            "email": "deleted@example.com",
            "code": "123456",
            "new_password": "NewPass456!",
        })
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()


class TestGenerateResetCode:
    """Tests for the reset code generation function."""

    def test_generate_reset_code_format(self):
        """Code is always 6 digits, 100000-999999."""
        for _ in range(100):
            code = generate_reset_code()
            assert len(code) == 6
            assert code.isdigit()
            assert 100000 <= int(code) <= 999999
