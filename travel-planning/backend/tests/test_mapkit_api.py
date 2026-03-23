"""Unit tests for Apple MapKit Server API client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import os

# Set minimal env vars before any app imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.models.enums import CongestionLevel  # noqa: E402
from app.schemas.eta import EtaResult  # noqa: E402
from app.services.mapkit_api import (  # noqa: E402
    MapKitError,
    parse_directions_response,
    validate_directions_response,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# --- validate_directions_response ---


class TestValidateDirectionsResponse:
    def test_normal_response_valid(self) -> None:
        data = _load_fixture("mapkit_directions_normal.json")
        assert validate_directions_response(data) is True

    def test_heavy_traffic_valid(self) -> None:
        data = _load_fixture("mapkit_directions_heavy_traffic.json")
        assert validate_directions_response(data) is True

    def test_no_traffic_valid(self) -> None:
        data = _load_fixture("mapkit_directions_no_traffic.json")
        assert validate_directions_response(data) is True

    def test_empty_routes_raises(self) -> None:
        data = _load_fixture("mapkit_directions_empty.json")
        with pytest.raises(MapKitError, match="No routes"):
            validate_directions_response(data)

    def test_missing_routes_key_raises(self) -> None:
        with pytest.raises(MapKitError, match="No routes"):
            validate_directions_response({"error": "something"})

    def test_missing_travel_time_raises(self) -> None:
        data = {"routes": [{"distanceMeters": 1000}]}
        with pytest.raises(MapKitError, match="Missing expectedTravelTime"):
            validate_directions_response(data)

    def test_duration_too_short_raises(self) -> None:
        data = {"routes": [{"expectedTravelTime": 30, "staticTravelTime": 30}]}
        with pytest.raises(MapKitError, match="outside valid range"):
            validate_directions_response(data)

    def test_duration_too_long_raises(self) -> None:
        data = {"routes": [{"expectedTravelTime": 100000, "staticTravelTime": 100000}]}
        with pytest.raises(MapKitError, match="outside valid range"):
            validate_directions_response(data)

    def test_extreme_traffic_ratio_raises(self) -> None:
        # 6x static — should fail sanity check
        data = {"routes": [{"expectedTravelTime": 12000, "staticTravelTime": 2000}]}
        with pytest.raises(MapKitError, match="sanity range"):
            validate_directions_response(data)

    def test_unrealistically_low_traffic_raises(self) -> None:
        # 40% of static — should fail
        data = {"routes": [{"expectedTravelTime": 400, "staticTravelTime": 1000}]}
        with pytest.raises(MapKitError, match="sanity range"):
            validate_directions_response(data)


# --- parse_directions_response ---


class TestParseDirectionsResponse:
    def test_normal_traffic(self) -> None:
        data = _load_fixture("mapkit_directions_normal.json")
        result = parse_directions_response(data)

        assert result.duration_seconds == 2100
        assert result.duration_in_traffic_seconds == 2580
        assert result.distance_meters == 77249
        # 2580/2100 = 1.228 -> moderate
        assert result.congestion_level == CongestionLevel.moderate
        assert 1.2 < result.traffic_ratio < 1.3

    def test_heavy_traffic(self) -> None:
        data = _load_fixture("mapkit_directions_heavy_traffic.json")
        result = parse_directions_response(data)

        assert result.duration_seconds == 2100
        assert result.duration_in_traffic_seconds == 4200
        # 4200/2100 = 2.0 -> severe
        assert result.congestion_level == CongestionLevel.severe
        assert result.traffic_ratio == 2.0

    def test_no_traffic(self) -> None:
        data = _load_fixture("mapkit_directions_no_traffic.json")
        result = parse_directions_response(data)

        assert result.duration_seconds == 1800
        assert result.duration_in_traffic_seconds == 1800
        assert result.distance_meters == 50000
        # 1800/1800 = 1.0 -> light
        assert result.congestion_level == CongestionLevel.light
        assert result.traffic_ratio == 1.0

    def test_missing_static_uses_travel_time(self) -> None:
        data = {"routes": [{"expectedTravelTime": 1800, "distanceMeters": 50000}]}
        result = parse_directions_response(data)

        # When staticTravelTime is missing, expectedTravelTime is used for both
        assert result.duration_seconds == 1800
        assert result.duration_in_traffic_seconds == 1800
        assert result.traffic_ratio == 1.0

    def test_empty_routes_raises(self) -> None:
        data = _load_fixture("mapkit_directions_empty.json")
        with pytest.raises(MapKitError):
            parse_directions_response(data)

    def test_missing_distance_defaults_to_zero(self) -> None:
        data = {"routes": [{"expectedTravelTime": 1800, "staticTravelTime": 1800}]}
        result = parse_directions_response(data)
        assert result.distance_meters == 0


# --- EtaResult caching ---


class TestEtaResultCaching:
    def test_round_trip_cache(self) -> None:
        data = _load_fixture("mapkit_directions_normal.json")
        original = parse_directions_response(data)

        cache_dict = original.to_cache_dict()
        restored = type(original).from_cache(cache_dict)

        assert restored.duration_seconds == original.duration_seconds
        assert (
            restored.duration_in_traffic_seconds
            == original.duration_in_traffic_seconds
        )
        assert restored.distance_meters == original.distance_meters
        assert restored.congestion_level == original.congestion_level
        assert restored.traffic_ratio == original.traffic_ratio

    def test_cache_dict_has_checked_at(self) -> None:
        data = _load_fixture("mapkit_directions_normal.json")
        result = parse_directions_response(data)
        cache_dict = result.to_cache_dict()
        assert "checked_at" in cache_dict


# --- Congestion level boundaries ---


class TestCongestionBoundaries:
    def test_light_at_1_0(self) -> None:
        result = EtaResult.from_route_response(1000, 1000, 10000)
        assert result.congestion_level == CongestionLevel.light

    def test_light_at_1_09(self) -> None:
        result = EtaResult.from_route_response(1000, 1090, 10000)
        assert result.congestion_level == CongestionLevel.light

    def test_moderate_at_1_1(self) -> None:
        result = EtaResult.from_route_response(1000, 1100, 10000)
        assert result.congestion_level == CongestionLevel.moderate

    def test_moderate_at_1_29(self) -> None:
        result = EtaResult.from_route_response(1000, 1290, 10000)
        assert result.congestion_level == CongestionLevel.moderate

    def test_heavy_at_1_3(self) -> None:
        result = EtaResult.from_route_response(1000, 1300, 10000)
        assert result.congestion_level == CongestionLevel.heavy

    def test_severe_at_1_6(self) -> None:
        result = EtaResult.from_route_response(1000, 1600, 10000)
        assert result.congestion_level == CongestionLevel.severe


# --- MapKitClient error handling ---


class TestMapKitClientErrors:
    """Tests for MapKitClient HTTP error handling using httpx.MockTransport."""

    @staticmethod
    def _generate_es256_pem() -> str:
        """Generate a fresh ES256 private key PEM for tests."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
        )

        key = ec.generate_private_key(ec.SECP256R1())
        return key.private_bytes(
            Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
        ).decode()

    @classmethod
    def _make_client(cls, handler) -> "MapKitClient":
        import httpx

        from app.services.mapkit_api import MapKitClient

        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        return MapKitClient(
            team_id="TEAMID",
            key_id="KEYID",
            private_key=cls._generate_es256_pem(),
            http_client=http_client,
        )

    @pytest.mark.asyncio
    async def test_timeout_raises_mapkit_error(self) -> None:
        import httpx

        from app.services.mapkit_api import MapKitError

        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("Connection timed out")

        client = self._make_client(timeout_handler)
        with pytest.raises(MapKitError, match="timed out"):
            await client.compute_route(37.77, -122.42, 37.33, -121.89)

    @pytest.mark.asyncio
    async def test_401_clears_token_cache(self) -> None:
        from app.services.mapkit_api import MapKitError

        def auth_fail_handler(request) -> "httpx.Response":
            import httpx

            return httpx.Response(401, text="Unauthorized")

        client = self._make_client(auth_fail_handler)

        # Pre-warm the token cache
        client._generate_token()
        assert client._token is not None

        with pytest.raises(MapKitError, match="Authentication failed"):
            await client.compute_route(37.77, -122.42, 37.33, -121.89)

        # Token cache should be cleared
        assert client._token is None

    @pytest.mark.asyncio
    async def test_429_raises_rate_limited(self) -> None:
        from app.services.mapkit_api import MapKitRateLimited

        def rate_limit_handler(request) -> "httpx.Response":
            import httpx

            return httpx.Response(429, text="Too Many Requests")

        client = self._make_client(rate_limit_handler)
        with pytest.raises(MapKitRateLimited):
            await client.compute_route(37.77, -122.42, 37.33, -121.89)
