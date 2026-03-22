"""Traffic client protocol and fallback wrapper.

Defines the TrafficClient protocol that both Google and TomTom
implementations follow, plus a FallbackTrafficClient that switches
to the secondary provider on failure.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.schemas.eta import EtaResult
from app.services.rate_limiter import RateLimitExceeded

logger = logging.getLogger(__name__)


class ProviderUnavailable(Exception):
    """Raised when a traffic data provider is unavailable."""


@runtime_checkable
class TrafficClient(Protocol):
    """Protocol for traffic ETA providers."""

    async def get_eta(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        departure_time: datetime | None = None,
    ) -> EtaResult: ...


class FallbackTrafficClient:
    """Traffic client that falls back to a secondary provider on failure.

    Wraps a primary provider (Google) and a fallback (TomTom). If the
    primary raises RateLimitExceeded or ProviderUnavailable, the fallback
    is used instead.
    """

    def __init__(
        self,
        primary: TrafficClient,
        fallback: TrafficClient,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self._primary_failures = 0
        self._max_failures_before_switch = 5

    async def get_eta(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        departure_time: datetime | None = None,
    ) -> EtaResult:
        """Get ETA from primary, falling back to secondary on failure."""
        # If primary has failed too many times, go straight to fallback
        if self._primary_failures >= self._max_failures_before_switch:
            logger.warning(
                f"Primary provider has {self._primary_failures} consecutive "
                f"failures — using fallback directly"
            )
            try:
                result = await self.fallback.get_eta(
                    origin_lat, origin_lng, dest_lat, dest_lng, departure_time
                )
                return result
            except Exception:
                logger.exception("Fallback provider also failed")
                raise ProviderUnavailable("Both providers unavailable")

        try:
            result = await self.primary.get_eta(
                origin_lat, origin_lng, dest_lat, dest_lng, departure_time
            )
            self._primary_failures = 0  # Reset on success
            return result
        except (RateLimitExceeded, ProviderUnavailable) as e:
            self._primary_failures += 1
            logger.warning(
                f"Primary provider failed ({e}), "
                f"falling back (failure #{self._primary_failures})"
            )
            try:
                return await self.fallback.get_eta(
                    origin_lat, origin_lng, dest_lat, dest_lng, departure_time
                )
            except Exception:
                logger.exception("Fallback provider also failed")
                raise ProviderUnavailable("Both providers unavailable") from e

    def reset_primary(self) -> None:
        """Reset the primary failure counter (e.g., after manual intervention)."""
        self._primary_failures = 0
