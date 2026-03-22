"""Google Routes API client for traffic-aware ETA computation."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from app.schemas.eta import EtaResult

logger = logging.getLogger(__name__)

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

FIELD_MASK = (
    "routes.duration,"
    "routes.staticDuration,"
    "routes.distanceMeters,"
    "routes.travelAdvisory.speedReadingIntervals"
)


class GoogleRoutesError(Exception):
    """Base error for Google Routes API calls."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GoogleRoutesRateLimited(GoogleRoutesError):
    """Google returned 429 — rate limited."""


class GoogleRoutesBadRequest(GoogleRoutesError):
    """Google returned 400 — bad coordinates or request."""


def parse_duration(duration_str: str) -> int:
    """Parse a Google Routes duration string like '2580s' to seconds."""
    match = re.match(r"^(\d+)s$", duration_str)
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}")
    return int(match.group(1))


def validate_routes_response(response_json: dict) -> bool:
    """Validate a Google Routes API response for sanity."""
    if "routes" not in response_json or len(response_json["routes"]) == 0:
        raise GoogleRoutesError("No routes in response")

    route = response_json["routes"][0]

    if "duration" not in route:
        raise GoogleRoutesError("Missing duration in route")

    duration = parse_duration(route["duration"])
    if not (60 <= duration <= 86400):
        raise GoogleRoutesError(
            f"Duration {duration}s outside valid range (1 min to 24 hours)"
        )

    static_str = route.get("staticDuration", route["duration"])
    static = parse_duration(static_str)
    if static <= 0:
        raise GoogleRoutesError("Static duration must be positive")

    # Sanity: traffic duration should be between 50% and 500% of static
    if not (0.5 * static <= duration <= 5 * static):
        raise GoogleRoutesError(
            f"Traffic duration {duration}s is outside sanity range "
            f"relative to static {static}s"
        )

    return True


def parse_routes_response(response_json: dict) -> EtaResult:
    """Parse a validated Google Routes API response into an EtaResult."""
    validate_routes_response(response_json)

    route = response_json["routes"][0]
    duration_in_traffic = parse_duration(route["duration"])
    static_duration = parse_duration(
        route.get("staticDuration", route["duration"])
    )
    distance_meters = route.get("distanceMeters", 0)

    return EtaResult.from_route_response(
        duration_seconds=static_duration,
        duration_in_traffic_seconds=duration_in_traffic,
        distance_meters=distance_meters,
    )


class GoogleRoutesClient:
    """Async client for the Google Routes API."""

    def __init__(self, api_key: str, http_client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = http_client

    async def compute_route(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        departure_time: datetime | None = None,
    ) -> EtaResult:
        """Compute a route and return the parsed ETA result."""
        body: dict = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": origin_lat,
                        "longitude": origin_lng,
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": dest_lat,
                        "longitude": dest_lng,
                    }
                }
            },
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "computeAlternativeRoutes": False,
            "languageCode": "en-US",
            "units": "IMPERIAL",
        }

        if departure_time is not None:
            # Ensure UTC
            if departure_time.tzinfo is None:
                departure_time = departure_time.replace(tzinfo=timezone.utc)
            body["departureTime"] = departure_time.isoformat()

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }

        try:
            response = await self.client.post(
                ROUTES_URL,
                json=body,
                headers=headers,
                timeout=10.0,
            )
        except httpx.TimeoutException as e:
            raise GoogleRoutesError("Request timed out") from e
        except httpx.HTTPError as e:
            raise GoogleRoutesError(f"HTTP error: {e}") from e

        if response.status_code == 400:
            raise GoogleRoutesBadRequest(
                f"Bad request: {response.text}", status_code=400
            )
        if response.status_code == 403:
            raise GoogleRoutesError(
                "API key invalid or quota exceeded", status_code=403
            )
        if response.status_code == 429:
            raise GoogleRoutesRateLimited(
                "Rate limited by Google", status_code=429
            )
        if response.status_code >= 500:
            raise GoogleRoutesError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except Exception as e:
            raise GoogleRoutesError(f"Invalid JSON response: {e}") from e

        return parse_routes_response(data)
