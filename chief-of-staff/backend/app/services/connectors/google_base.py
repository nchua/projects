"""Shared Google OAuth logic for Calendar and Gmail connectors."""

import logging
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials

from app.core.config import get_settings
from app.models.integration import Integration
from app.services.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class GoogleBaseConnector(BaseConnector):
    """Base class for Google API connectors with shared OAuth handling.

    Subclasses must set `scopes` and implement `sync`.
    """

    scopes: list[str]

    def _build_credentials(self) -> Credentials:
        """Build Google OAuth2 credentials from stored tokens."""
        settings = get_settings()
        return Credentials(
            token=self._decrypt_auth_token(),
            refresh_token=self._decrypt_refresh_token(),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=self.scopes,
        )

    async def authenticate(self) -> bool:
        """Validate credentials and refresh if needed."""
        try:
            creds = self._build_credentials()

            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request

                creds.refresh(Request())

                self.integration.encrypted_auth_token = self._encrypt(creds.token)
                if creds.refresh_token:
                    self.integration.encrypted_refresh_token = self._encrypt(
                        creds.refresh_token
                    )

            self._mark_healthy()
            return True
        except Exception as e:
            logger.error("%s auth failed: %s", self.provider.value, e)
            self._mark_error(str(e))
            return False

    async def refresh_token_if_needed(self) -> bool:
        """Proactive token refresh at 75% of lifetime."""
        try:
            creds = self._build_credentials()
            if creds.expired or (
                creds.expiry
                and creds.expiry - datetime.now(timezone.utc) < timedelta(minutes=15)
            ):
                return await self.authenticate()
            return True
        except Exception as e:
            logger.error("Token refresh check failed: %s", e)
            return False

    async def _ensure_credentials(self) -> Credentials | None:
        """Build credentials, re-authenticating if expired.

        Returns:
            Valid Credentials, or None if authentication failed.
        """
        creds = self._build_credentials()
        if creds.expired:
            if not await self.authenticate():
                return None
            creds = self._build_credentials()
        return creds
