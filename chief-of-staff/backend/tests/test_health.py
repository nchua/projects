"""Smoke tests for health, auth flow, and encryption."""



class TestHealth:
    """Health endpoint tests."""

    def test_health_returns_200(self, client):
        """GET /health returns 200 with app name."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "Chief of Staff" in data["app"]


class TestAuthFlow:
    """Authentication endpoint tests."""

    def test_register_creates_user(self, client):
        """POST /api/v1/auth/register creates a new user."""
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com", "password": "TestPass123!"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert "id" in data

    def test_register_duplicate_email(self, client):
        """Registering the same email twice returns 400."""
        payload = {"email": "dup@example.com", "password": "TestPass123!"}
        client.post("/api/v1/auth/register", json=payload)
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400

    def test_login_returns_tokens(self, client):
        """POST /api/v1/auth/login returns access and refresh tokens."""
        client.post(
            "/api/v1/auth/register",
            json={"email": "login@example.com", "password": "TestPass123!"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "TestPass123!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        """Login with wrong password returns 401."""
        client.post(
            "/api/v1/auth/register",
            json={"email": "wrong@example.com", "password": "TestPass123!"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@example.com", "password": "WrongPass456!"},
        )
        assert resp.status_code == 401

    def test_protected_endpoint_without_token(self, client):
        """GET /api/v1/auth/me without token returns 401/403."""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)

    def test_protected_endpoint_with_token(self, client):
        """GET /api/v1/auth/me with valid token returns user."""
        client.post(
            "/api/v1/auth/register",
            json={"email": "me@example.com", "password": "TestPass123!"},
        )
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "me@example.com", "password": "TestPass123!"},
        )
        token = login_resp.json()["access_token"]
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "me@example.com"

    def test_refresh_token(self, client):
        """POST /api/v1/auth/refresh returns new tokens."""
        client.post(
            "/api/v1/auth/register",
            json={"email": "refresh@example.com", "password": "TestPass123!"},
        )
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "refresh@example.com", "password": "TestPass123!"},
        )
        refresh_token = login_resp.json()["refresh_token"]
        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data


class TestEncryption:
    """Encryption round-trip tests."""

    def test_encrypt_decrypt_roundtrip(self):
        """encrypt_token -> decrypt_token returns original value."""
        from cryptography.fernet import Fernet

        # Generate a test key and patch settings
        test_key = Fernet.generate_key().decode("utf-8")

        from unittest.mock import patch, MagicMock

        mock_settings = MagicMock()
        mock_settings.token_encryption_key = test_key

        with patch("app.core.encryption.get_settings", return_value=mock_settings):
            from app.core.encryption import encrypt_token, decrypt_token

            original = "gho_test_oauth_token_12345"
            encrypted = encrypt_token(original)
            assert encrypted != original
            decrypted = decrypt_token(encrypted)
            assert decrypted == original

    def test_generate_key(self):
        """generate_key returns a valid Fernet key."""
        from app.core.encryption import generate_key
        from cryptography.fernet import Fernet

        key = generate_key()
        # Should not raise
        Fernet(key.encode("utf-8"))
