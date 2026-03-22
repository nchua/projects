"""Unit tests for push notification sender — content building and payload."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from app.services.push_sender import (
    TIER_APNS_CONFIG,
    build_fcm_payload,
    build_notification,
)


def _make_trip(
    name: str = "Brunch",
    arrival_time: datetime | None = None,
    last_eta_seconds: int = 1320,  # 22 min
    dest_address: str = "The Mill",
    dest_lat: float = 37.7649,
    dest_lng: float = -122.4294,
) -> MagicMock:
    trip = MagicMock()
    trip.id = "test-trip-id"
    trip.name = name
    trip.arrival_time = arrival_time or datetime(
        2026, 3, 22, 18, 0, 0, tzinfo=timezone.utc
    )
    trip.last_eta_seconds = last_eta_seconds
    trip.dest_address = dest_address
    trip.dest_lat = dest_lat
    trip.dest_lng = dest_lng
    trip.buffer_minutes = 15
    trip.notification_count = 0
    trip.user_id = "test-user-id"
    return trip


def _make_user(tz: str = "America/Los_Angeles") -> MagicMock:
    user = MagicMock()
    user.timezone = tz
    return user


class TestBuildNotification:
    @freeze_time("2026-03-22T17:00:00Z")
    def test_heads_up_content(self) -> None:
        trip = _make_trip()
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "heads_up", departure, "initial")
        assert "Brunch" in title
        assert "min" in title  # "Brunch in X min"
        assert "leave by" in body.lower()

    @freeze_time("2026-03-22T17:00:00Z")
    def test_prepare_worse_content(self) -> None:
        trip = _make_trip()
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "prepare", departure, "worse")
        assert "earlier" in title.lower()
        assert "traffic" in body.lower()

    @freeze_time("2026-03-22T17:00:00Z")
    def test_prepare_better_content(self) -> None:
        trip = _make_trip()
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 30, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "prepare", departure, "better")
        assert "cleared" in title.lower()

    @freeze_time("2026-03-22T17:00:00Z")
    def test_prepare_initial_content(self) -> None:
        trip = _make_trip()
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "prepare", departure, "initial")
        assert "leave by" in title.lower()

    @freeze_time("2026-03-22T17:00:00Z")
    def test_leave_soon_content(self) -> None:
        trip = _make_trip()
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 10, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "leave_soon", departure, "worse")
        assert "leave soon" in title.lower()
        assert "current traffic" in body.lower()

    @freeze_time("2026-03-22T17:00:00Z")
    def test_leave_now_content(self) -> None:
        trip = _make_trip()
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 0, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "leave_now", departure, "initial")
        assert "time to leave" in title.lower()
        assert "leave now" in body.lower()

    @freeze_time("2026-03-22T17:00:00Z")
    def test_running_late_content(self) -> None:
        trip = _make_trip()
        user = _make_user()
        # Departure was 10 min ago
        departure = datetime(2026, 3, 22, 16, 50, tzinfo=timezone.utc)

        title, body = build_notification(
            trip, user, "running_late", departure, "worse"
        )
        assert "running late" in title.lower()
        assert "behind" in body.lower()
        assert "navigate" in body.lower()

    @freeze_time("2026-03-22T17:00:00Z")
    def test_long_destination_name(self) -> None:
        trip = _make_trip(name="The Very Long Restaurant Name That Goes On Forever")
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "leave_now", departure, "initial")
        # Should not crash with long names
        assert len(title) > 0
        assert len(body) > 0

    @freeze_time("2026-03-22T17:00:00Z")
    def test_no_name_uses_address(self) -> None:
        trip = _make_trip(name="")
        user = _make_user()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        title, body = build_notification(trip, user, "leave_soon", departure, "initial")
        assert "The Mill" in title  # Falls back to dest_address


class TestBuildFcmPayload:
    @freeze_time("2026-03-22T17:00:00Z")
    def test_payload_structure(self) -> None:
        trip = _make_trip()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        payload = build_fcm_payload(
            token="fake-device-fcm-placeholder",
            trip=trip,
            tier="leave_soon",
            title="Leave soon for Brunch",
            body="Leave by 10:23 AM to arrive by 11:00 AM.",
            departure_time=departure,
        )

        assert payload["token"] == "fake-device-fcm-placeholder"
        assert payload["title"] == "Leave soon for Brunch"
        assert "data" in payload
        assert payload["data"]["trip_id"] == "test-trip-id"
        assert payload["data"]["tier"] == "leave_soon"
        assert "deep_link" in payload["data"]
        assert "apns" in payload
        assert payload["apns"]["headers"]["apns-priority"] == "10"

    @freeze_time("2026-03-22T17:00:00Z")
    def test_silent_payload(self) -> None:
        trip = _make_trip()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        payload = build_fcm_payload(
            token="fake-device-fcm-placeholder",
            trip=trip,
            tier="heads_up",
            title="Title",
            body="Body",
            departure_time=departure,
            silent=True,
        )

        aps = payload["apns"]["payload"]["aps"]
        assert aps.get("content-available") == 1
        assert "alert" not in aps
        assert payload["apns"]["headers"]["apns-push-type"] == "background"

    @freeze_time("2026-03-22T17:00:00Z")
    def test_per_tier_priority(self) -> None:
        trip = _make_trip()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        for tier, config in TIER_APNS_CONFIG.items():
            payload = build_fcm_payload(
                token="fcm-placeholder", trip=trip, tier=tier,
                title="T", body="B", departure_time=departure,
            )
            assert payload["apns"]["headers"]["apns-priority"] == config["priority"]

    @freeze_time("2026-03-22T17:00:00Z")
    def test_data_payload_has_all_fields(self) -> None:
        trip = _make_trip()
        departure = datetime(2026, 3, 22, 17, 23, tzinfo=timezone.utc)

        payload = build_fcm_payload(
            token="fcm-placeholder", trip=trip, tier="prepare",
            title="T", body="B", departure_time=departure,
        )

        data = payload["data"]
        expected_keys = {
            "trip_id", "tier", "recommended_departure",
            "eta_seconds", "arrival_time", "dest_lat", "dest_lng", "deep_link",
        }
        assert expected_keys.issubset(set(data.keys()))
