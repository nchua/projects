"""Unit tests for Google Routes API client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import os
import sys

# Set minimal env vars before any app imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# Install deps if needed
from app.models.enums import CongestionLevel  # noqa: E402
from app.schemas.eta import EtaResult  # noqa: E402
from app.services.google_routes import (  # noqa: E402
    GoogleRoutesError,
    parse_duration,
    parse_routes_response,
    validate_routes_response,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# --- parse_duration ---


class TestParseDuration:
    def test_normal_duration(self) -> None:
        assert parse_duration("2580s") == 2580

    def test_short_duration(self) -> None:
        assert parse_duration("60s") == 60

    def test_long_duration(self) -> None:
        assert parse_duration("86400s") == 86400

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_duration("25 minutes")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_duration("")

    def test_no_s_suffix_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_duration("2580")


# --- validate_routes_response ---


class TestValidateRoutesResponse:
    def test_normal_response_valid(self) -> None:
        data = _load_fixture("google_routes_normal.json")
        assert validate_routes_response(data) is True

    def test_heavy_traffic_valid(self) -> None:
        data = _load_fixture("google_routes_heavy_traffic.json")
        assert validate_routes_response(data) is True

    def test_no_traffic_valid(self) -> None:
        data = _load_fixture("google_routes_no_traffic.json")
        assert validate_routes_response(data) is True

    def test_empty_routes_raises(self) -> None:
        data = _load_fixture("google_routes_empty.json")
        with pytest.raises(GoogleRoutesError, match="No routes"):
            validate_routes_response(data)

    def test_missing_routes_key_raises(self) -> None:
        with pytest.raises(GoogleRoutesError, match="No routes"):
            validate_routes_response({"error": "something"})

    def test_missing_duration_raises(self) -> None:
        data = {"routes": [{"distanceMeters": 1000}]}
        with pytest.raises(GoogleRoutesError, match="Missing duration"):
            validate_routes_response(data)

    def test_duration_too_short_raises(self) -> None:
        data = {"routes": [{"duration": "30s", "staticDuration": "30s"}]}
        with pytest.raises(GoogleRoutesError, match="outside valid range"):
            validate_routes_response(data)

    def test_duration_too_long_raises(self) -> None:
        data = {"routes": [{"duration": "100000s", "staticDuration": "100000s"}]}
        with pytest.raises(GoogleRoutesError, match="outside valid range"):
            validate_routes_response(data)

    def test_extreme_traffic_ratio_raises(self) -> None:
        # 6x static — should fail sanity check
        data = {"routes": [{"duration": "12000s", "staticDuration": "2000s"}]}
        with pytest.raises(GoogleRoutesError, match="sanity range"):
            validate_routes_response(data)

    def test_unrealistically_low_traffic_raises(self) -> None:
        # 40% of static — should fail
        data = {"routes": [{"duration": "400s", "staticDuration": "1000s"}]}
        with pytest.raises(GoogleRoutesError, match="sanity range"):
            validate_routes_response(data)


# --- parse_routes_response ---


class TestParseRoutesResponse:
    def test_normal_traffic(self) -> None:
        data = _load_fixture("google_routes_normal.json")
        result = parse_routes_response(data)

        assert result.duration_seconds == 2100
        assert result.duration_in_traffic_seconds == 2580
        assert result.distance_meters == 77249
        # 2580/2100 = 1.228 -> moderate
        assert result.congestion_level == CongestionLevel.moderate
        assert 1.2 < result.traffic_ratio < 1.3

    def test_heavy_traffic(self) -> None:
        data = _load_fixture("google_routes_heavy_traffic.json")
        result = parse_routes_response(data)

        assert result.duration_seconds == 2100
        assert result.duration_in_traffic_seconds == 4200
        # 4200/2100 = 2.0 -> severe
        assert result.congestion_level == CongestionLevel.severe
        assert result.traffic_ratio == 2.0

    def test_no_traffic(self) -> None:
        data = _load_fixture("google_routes_no_traffic.json")
        result = parse_routes_response(data)

        assert result.duration_seconds == 1800
        assert result.duration_in_traffic_seconds == 1800
        assert result.distance_meters == 50000
        # 1800/1800 = 1.0 -> light
        assert result.congestion_level == CongestionLevel.light
        assert result.traffic_ratio == 1.0

    def test_missing_static_duration_uses_duration(self) -> None:
        data = {"routes": [{"duration": "1800s", "distanceMeters": 50000}]}
        result = parse_routes_response(data)

        # When staticDuration is missing, duration is used for both
        assert result.duration_seconds == 1800
        assert result.duration_in_traffic_seconds == 1800
        assert result.traffic_ratio == 1.0

    def test_empty_routes_raises(self) -> None:
        data = _load_fixture("google_routes_empty.json")
        with pytest.raises(GoogleRoutesError):
            parse_routes_response(data)

    def test_missing_distance_defaults_to_zero(self) -> None:
        data = {"routes": [{"duration": "1800s", "staticDuration": "1800s"}]}
        result = parse_routes_response(data)
        assert result.distance_meters == 0


# --- EtaResult caching ---


class TestEtaResultCaching:
    def test_round_trip_cache(self) -> None:
        data = _load_fixture("google_routes_normal.json")
        original = parse_routes_response(data)

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
        data = _load_fixture("google_routes_normal.json")
        result = parse_routes_response(data)
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
