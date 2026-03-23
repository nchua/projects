"""Tests for Phase 1B: Integration Layer."""

from unittest.mock import MagicMock, patch

from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.enums import IntegrationProvider
from app.models.integration import Integration
from app.models.user import User
from app.services.audit_log import log_audit
from app.services.connectors.base import BaseConnector, SyncResult
from app.services.connectors.gmail import (
    hash_content,
    html_to_text,
    strip_email_noise,
    truncate_for_api,
)


class TestSyncResult:
    """Tests for the SyncResult dataclass."""

    def test_defaults(self):
        result = SyncResult()
        assert result.documents_fetched == 0
        assert result.new_cursor is None
        assert result.raw_items == []
        assert result.errors == []

    def test_with_data(self):
        result = SyncResult(
            documents_fetched=5,
            new_cursor="abc123",
            raw_items=[{"id": "1"}],
            errors=["test error"],
        )
        assert result.documents_fetched == 5
        assert result.new_cursor == "abc123"
        assert len(result.raw_items) == 1
        assert len(result.errors) == 1


class TestBaseConnector:
    """Tests for BaseConnector helper methods."""

    def _create_user(self, db_session):
        """Create a test user for FK constraints."""
        user = User(
            email="connector@example.com",
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(user)
        db_session.flush()
        return user

    def test_mark_error_increments_count(self, db_session):
        user = self._create_user(db_session)
        integration = Integration(
            user_id=user.id,
            provider="github",
            status="healthy",
            error_count=0,
        )
        db_session.add(integration)
        db_session.flush()

        # Create a concrete subclass for testing
        class _TestConnector(BaseConnector):
            provider = IntegrationProvider.GITHUB
            async def authenticate(self):
                return True
            async def sync(self, sync_state):
                return SyncResult()

        connector = _TestConnector(integration)
        connector._mark_error("test error")

        assert integration.error_count == 1
        assert integration.last_error == "test error"
        assert integration.status == "degraded"

    def test_mark_error_fails_after_three(self, db_session):
        user = self._create_user(db_session)
        integration = Integration(
            user_id=user.id,
            provider="github",
            status="healthy",
            error_count=2,
        )
        db_session.add(integration)
        db_session.flush()

        class _TestConnector(BaseConnector):
            provider = IntegrationProvider.GITHUB
            async def authenticate(self):
                return True
            async def sync(self, sync_state):
                return SyncResult()

        connector = _TestConnector(integration)
        connector._mark_error("third error")

        assert integration.error_count == 3
        assert integration.status == "failed"

    def test_mark_healthy_resets(self, db_session):
        user = self._create_user(db_session)
        integration = Integration(
            user_id=user.id,
            provider="github",
            status="degraded",
            error_count=2,
            last_error="old error",
        )
        db_session.add(integration)
        db_session.flush()

        class _TestConnector(BaseConnector):
            provider = IntegrationProvider.GITHUB
            async def authenticate(self):
                return True
            async def sync(self, sync_state):
                return SyncResult()

        connector = _TestConnector(integration)
        connector._mark_healthy()

        assert integration.error_count == 0
        assert integration.last_error is None
        assert integration.status == "healthy"
        assert integration.last_synced_at is not None


class TestGmailUtilities:
    """Tests for Gmail connector utility functions."""

    def test_html_to_text_basic(self):
        html = "<p>Hello <b>world</b></p>"
        assert "Hello world" in html_to_text(html)

    def test_html_to_text_strips_scripts(self):
        html = "<p>Hello</p><script>alert('x')</script><p>world</p>"
        text = html_to_text(html)
        assert "alert" not in text
        assert "Hello" in text
        assert "world" in text

    def test_html_to_text_adds_newlines_for_blocks(self):
        html = "<div>Line 1</div><div>Line 2</div>"
        text = html_to_text(html)
        assert "Line 1" in text
        assert "Line 2" in text

    def test_strip_email_noise_removes_quotes(self):
        text = "Hello\n> quoted line\n> another quote"
        cleaned = strip_email_noise(text)
        assert "quoted line" not in cleaned
        assert "Hello" in cleaned

    def test_strip_email_noise_breaks_at_on_wrote(self):
        text = "Important message\n\nOn Mon, Jan 1 wrote:\nOld content"
        cleaned = strip_email_noise(text)
        assert "Important message" in cleaned
        assert "Old content" not in cleaned

    def test_strip_email_noise_breaks_at_signature(self):
        text = "Real content\n--\nJohn Doe\nSenior Engineer"
        cleaned = strip_email_noise(text)
        assert "Real content" in cleaned
        assert "John Doe" not in cleaned

    def test_strip_email_noise_removes_unsubscribe(self):
        text = "Content here\nClick to unsubscribe from this list"
        cleaned = strip_email_noise(text)
        assert "Content here" in cleaned
        assert "unsubscribe" not in cleaned

    def test_truncate_for_api_short_text(self):
        text = "short"
        assert truncate_for_api(text) == "short"

    def test_truncate_for_api_long_text(self):
        text = "a" * 10000
        result = truncate_for_api(text, max_chars=100)
        assert len(result) == 100 + len("\n[truncated]")
        assert result.endswith("[truncated]")

    def test_hash_content_deterministic(self):
        h1 = hash_content("hello world")
        h2 = hash_content("hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_hash_content_differs(self):
        h1 = hash_content("hello")
        h2 = hash_content("world")
        assert h1 != h2


class TestAuditLog:
    """Tests for the audit logging service."""

    def test_log_audit_creates_entry(self, db_session):
        entry = log_audit(
            db_session,
            "test_action",
            user_id="user-123",
            integration_id="int-456",
            metadata={"key": "value"},
        )
        assert entry.action_type == "test_action"
        assert entry.user_id == "user-123"
        assert entry.integration_id == "int-456"
        assert entry.success is True
        assert entry.metadata_ == {"key": "value"}

    def test_log_audit_failure(self, db_session):
        entry = log_audit(
            db_session,
            "failed_action",
            success=False,
            error_details="Something went wrong",
        )
        assert entry.success is False
        assert entry.error_details == "Something went wrong"

    def test_log_audit_persists(self, db_session):
        log_audit(db_session, "persist_test", user_id="test")
        db_session.flush()

        entries = db_session.query(AuditLog).filter(
            AuditLog.action_type == "persist_test"
        ).all()
        assert len(entries) == 1


class TestIntegrationEndpoints:
    """Tests for the integration API endpoints."""

    def _register_and_login(self, client):
        """Helper to create a user and get auth token."""
        client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "TestPass123",
        })
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "TestPass123",
        })
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_list_integrations_empty(self, client):
        headers = self._register_and_login(client)
        response = client.get("/api/v1/integrations", headers=headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_integrations_requires_auth(self, client):
        response = client.get("/api/v1/integrations")
        assert response.status_code == 403

    def test_health_endpoint(self, client):
        headers = self._register_and_login(client)
        response = client.get("/api/v1/integrations/health", headers=headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_google_authorize_returns_url(self, client):
        headers = self._register_and_login(client)
        with patch("app.api.integrations.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                google_client_id="test-client-id",
                google_client_secret="test-secret",
            )
            response = client.post(
                "/api/v1/integrations/google/authorize",
                params={"redirect_uri": "http://localhost:3000/callback"},
                headers=headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "accounts.google.com" in data["authorization_url"]
        assert "test-client-id" in data["authorization_url"]

    def test_github_authorize_returns_url(self, client):
        headers = self._register_and_login(client)
        with patch("app.api.integrations.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                github_client_id="gh-client-id",
                github_client_secret="gh-secret",
            )
            response = client.post(
                "/api/v1/integrations/github/authorize",
                params={"redirect_uri": "http://localhost:3000/callback"},
                headers=headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "github.com" in data["authorization_url"]

    def test_disconnect_nonexistent(self, client):
        headers = self._register_and_login(client)
        response = client.delete(
            "/api/v1/integrations/nonexistent-id",
            headers=headers,
        )
        assert response.status_code == 404

    def test_panic_with_no_integrations(self, client):
        headers = self._register_and_login(client)
        response = client.post("/api/v1/integrations/panic", headers=headers)
        assert response.status_code == 204
