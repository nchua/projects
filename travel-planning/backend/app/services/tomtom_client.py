"""TomTom Routing API client — fallback traffic provider.

Used when Google Routes API is unavailable or rate-limited.
Cost: $0.75/1k requests vs Google's $10/1k.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from app.schemas.eta import EtaResult
from app.services.traffic_client import ProviderUnavailable

logger = logging.getLogger(__name__)

TOMTOM_BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute"


class TomTomClient:
    """Async client for the TomTom Routing API."""

    def __init__(self, api_key: str, http_client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = http_client

    async def get_eta(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        departure_time: datetime | None = None,
    ) -> EtaResult:
        """Compute a route via TomTom and return an EtaResult."""
        coords = f"{origin_lat},{origin_lng}:{dest_lat},{dest_lng}"
        url = f"{TOMTOM_BASE_URL}/{coords}/json"

        params: dict[str, str] = {
            "key": self.api_key,
            "traffic": "true",
            "travelMode": "car",
        }

        if departure_time is not None:
            if departure_time.tzinfo is None:
                departure_time = departure_time.replace(tzinfo=timezone.utc)
            params["departAt"] = departure_time.strftime("%Y-%m-%dT%H:%M:%S")

        try:
            response = await self.client.get(url, params=params, timeout=10.0)
        except httpx.TimeoutException as e:
            raise ProviderUnavailable("TomTom request timed out") from e
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"TomTom HTTP error: {e}") from e

        if response.status_code != 200:
            raise ProviderUnavailable(
                f"TomTom returned {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except Exception as e:
            raise ProviderUnavailable(f"TomTom invalid JSON: {e}") from e

        return self._parse_response(data)

    def _parse_response(self, data: dict) -> EtaResult:
        """Parse a TomTom routing response into an EtaResult."""
        try:
            route = data["routes"][0]
            summary = route["summary"]

            travel_time = summary["travelTimeInSeconds"]
            no_traffic_time = summary.get(
                "noTrafficTravelTimeInSeconds", travel_time
            )
            distance = summary.get("lengthInMeters", 0)

            return EtaResult.from_route_response(
                duration_seconds=no_traffic_time,
                duration_in_traffic_seconds=travel_time,
                distance_meters=distance,
            )
        except (KeyError, IndexError) as e:
            raise ProviderUnavailable(
                f"TomTom response missing expected fields: {e}"
            ) from e
