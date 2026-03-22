"""Apple MapKit Server API client for traffic-aware ETA computation.

Uses JWT-authenticated requests to Apple's Maps Server API for
directions, ETAs, and geocoding.

Auth: ES256 JWT signed with your MapKit private key.
Docs: https://developer.apple.com/documentation/mapkitjs/creating_a_maps_token
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx
import jwt

from app.schemas.eta import EtaResult

logger = logging.getLogger(__name__)

MAPKIT_BASE_URL = "https://maps-api.apple.com"
DIRECTIONS_URL = f"{MAPKIT_BASE_URL}/v1/directions"
ETA_URL = f"{MAPKIT_BASE_URL}/v1/etas"
GEOCODE_URL = f"{MAPKIT_BASE_URL}/v1/geocode"

# JWT lifetime — Apple allows up to 30 minutes
JWT_LIFETIME_SECONDS = 1800


class MapKitError(Exception):
    """Base error for MapKit Server API calls."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MapKitRateLimited(MapKitError):
    """Apple returned 429 — rate limited."""


class MapKitBadRequest(MapKitError):
    """Apple returned 400 — bad coordinates or request."""


class MapKitClient:
    """Async client for the Apple MapKit Server API."""

    def __init__(
        self,
        team_id: str,
        key_id: str,
        private_key: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self.team_id = team_id
        self.key_id = key_id
        self.private_key = private_key
        self.client = http_client
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _generate_token(self) -> str:
        """Generate a MapKit Server API JWT token."""
        now = time.time()

        # Reuse token if still valid (with 60s buffer)
        if self._token and self._token_expires_at > now + 60:
            return self._token

        payload = {
            "iss": self.team_id,
            "iat": int(now),
            "exp": int(now + JWT_LIFETIME_SECONDS),
        }
        headers = {
            "kid": self.key_id,
            "typ": "JWT",
            "alg": "ES256",
        }

        self._token = jwt.encode(
            payload, self.private_key, algorithm="ES256", headers=headers
        )
        self._token_expires_at = now + JWT_LIFETIME_SECONDS
        return self._token

    def _auth_headers(self) -> dict[str, str]:
        """Get authorization headers with a fresh JWT."""
        token = self._generate_token()
        return {"Authorization": f"Bearer {token}"}

    async def compute_route(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        departure_time: datetime | None = None,
    ) -> EtaResult:
        """Compute a route using MapKit Directions and return the parsed ETA.

        Uses /v1/directions which returns traffic-aware travel time when
        a departureDate is provided.
        """
        params: dict[str, str] = {
            "origin": f"{origin_lat},{origin_lng}",
            "destination": f"{dest_lat},{dest_lng}",
            "transportType": "Automobile",
        }

        if departure_time is not None:
            if departure_time.tzinfo is None:
                departure_time = departure_time.replace(tzinfo=timezone.utc)
            params["departureDate"] = departure_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            response = await self.client.get(
                DIRECTIONS_URL,
                params=params,
                headers=self._auth_headers(),
                timeout=10.0,
            )
        except httpx.TimeoutException as e:
            raise MapKitError("Request timed out") from e
        except httpx.HTTPError as e:
            raise MapKitError(f"HTTP error: {e}") from e

        if response.status_code == 400:
            raise MapKitBadRequest(
                f"Bad request: {response.text}", status_code=400
            )
        if response.status_code == 401:
            # Token expired or invalid — clear cache and report
            self._token = None
            raise MapKitError("Authentication failed — check MapKit credentials", status_code=401)
        if response.status_code == 429:
            raise MapKitRateLimited(
                "Rate limited by Apple", status_code=429
            )
        if response.status_code >= 500:
            raise MapKitError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except Exception as e:
            raise MapKitError(f"Invalid JSON response: {e}") from e

        return parse_directions_response(data)

    async def geocode(self, address: str) -> dict[str, float] | None:
        """Geocode an address to lat/lng using MapKit Server API.

        Returns {"lat": float, "lng": float} or None if not found.
        """
        params = {"q": address}

        try:
            response = await self.client.get(
                GEOCODE_URL,
                params=params,
                headers=self._auth_headers(),
                timeout=10.0,
            )
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.error(f"Geocoding error: {e}")
            return None

        if response.status_code != 200:
            logger.warning(f"Geocoding returned {response.status_code}")
            return None

        data = response.json()
        results = data.get("results", [])
        if not results:
            return None

        coord = results[0].get("coordinate", {})
        lat = coord.get("latitude")
        lng = coord.get("longitude")
        if lat is not None and lng is not None:
            return {"lat": lat, "lng": lng}
        return None


def validate_directions_response(response_json: dict) -> bool:
    """Validate a MapKit Directions API response for sanity."""
    routes = response_json.get("routes", [])
    if not routes:
        raise MapKitError("No routes in response")

    route = routes[0]

    # MapKit returns expectedTravelTime in seconds (integer)
    duration = route.get("expectedTravelTime")
    if duration is None:
        raise MapKitError("Missing expectedTravelTime in route")

    duration = int(duration)
    if not (60 <= duration <= 86400):
        raise MapKitError(
            f"Duration {duration}s outside valid range (1 min to 24 hours)"
        )

    # staticTravelTime is the no-traffic baseline (available when departureDate is set)
    static = route.get("staticTravelTime")
    if static is not None:
        static = int(static)
        if static <= 0:
            raise MapKitError("Static travel time must be positive")
        # Sanity: traffic duration should be between 50% and 500% of static
        if not (0.5 * static <= duration <= 5 * static):
            raise MapKitError(
                f"Traffic duration {duration}s is outside sanity range "
                f"relative to static {static}s"
            )

    return True


def parse_directions_response(response_json: dict) -> EtaResult:
    """Parse a validated MapKit Directions API response into an EtaResult."""
    validate_directions_response(response_json)

    route = response_json["routes"][0]
    duration_in_traffic = int(route["expectedTravelTime"])

    # staticTravelTime is the no-traffic baseline; fall back to travel time
    static_duration = int(
        route.get("staticTravelTime", route["expectedTravelTime"])
    )
    distance_meters = int(route.get("distanceMeters", 0))

    return EtaResult.from_route_response(
        duration_seconds=static_duration,
        duration_in_traffic_seconds=duration_in_traffic,
        distance_meters=distance_meters,
    )
