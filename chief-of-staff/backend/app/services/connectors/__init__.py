"""Integration connectors for external services."""

from app.services.connectors.base import BaseConnector, SyncResult
from app.services.connectors.google_base import GoogleBaseConnector

__all__ = ["BaseConnector", "GoogleBaseConnector", "SyncResult"]
