"""Abstract base connector for all integration connectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.encryption import decrypt_token, encrypt_token
from app.models.enums import IntegrationProvider
from app.models.integration import Integration
from app.models.sync_state import SyncState


@dataclass
class SyncResult:
    """Result of a connector sync operation."""

    documents_fetched: int = 0
    new_cursor: str | None = None
    raw_items: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BaseConnector(ABC):
    """Base for all integration connectors.

    Each connector handles authentication, token refresh, and
    incremental data fetching for a specific provider.
    """

    provider: IntegrationProvider

    def __init__(self, integration: Integration) -> None:
        self.integration = integration
        self._http_client: httpx.AsyncClient | None = None

    async def get_http_client(self) -> httpx.AsyncClient:
        """Lazy-initialize a shared async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client if open."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    @abstractmethod
    async def authenticate(self) -> bool:
        """Validate and/or refresh credentials.

        Returns:
            True if authenticated successfully. Updates integration.status
            on failure.
        """

    @abstractmethod
    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch new data since last sync.

        Args:
            sync_state: The current sync cursor, or None for first sync.

        Returns:
            SyncResult with fetched items and new cursor position.
        """

    async def refresh_token_if_needed(self) -> bool:
        """Proactive token refresh at 75% of lifetime.

        Override in subclasses that use refresh tokens (Google).
        GitHub tokens are long-lived and don't need refresh.

        Returns:
            True if token was refreshed or still valid.
        """
        return True

    def _decrypt_auth_token(self) -> str:
        """Decrypt the stored OAuth access token."""
        if not self.integration.encrypted_auth_token:
            raise ValueError(f"No auth token for integration {self.integration.id}")
        return decrypt_token(self.integration.encrypted_auth_token)

    def _decrypt_refresh_token(self) -> str:
        """Decrypt the stored OAuth refresh token."""
        if not self.integration.encrypted_refresh_token:
            raise ValueError(f"No refresh token for integration {self.integration.id}")
        return decrypt_token(self.integration.encrypted_refresh_token)

    @staticmethod
    def _encrypt(plaintext: str) -> str:
        """Encrypt a token for storage."""
        return encrypt_token(plaintext)

    def _update_rate_limits(self, remaining: int | None, reset_at: datetime | None) -> None:
        """Update rate limit tracking on the integration model."""
        if remaining is not None:
            self.integration.rate_limit_remaining = remaining
        if reset_at is not None:
            self.integration.rate_limit_reset_at = reset_at

    def _mark_error(self, error: str) -> None:
        """Increment error count and record the error."""
        self.integration.error_count += 1
        self.integration.last_error = error
        if self.integration.error_count >= 3:
            self.integration.status = "failed"
        else:
            self.integration.status = "degraded"

    def _mark_healthy(self) -> None:
        """Reset error state after a successful operation."""
        self.integration.error_count = 0
        self.integration.last_error = None
        self.integration.status = "healthy"
        self.integration.last_synced_at = datetime.now(tz=timezone.utc)
