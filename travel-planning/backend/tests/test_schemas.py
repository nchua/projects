"""Tests for Pydantic schema validation."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.trip import CreateTripRequest
from app.schemas.user import UpdateUserRequest


class TestCreateTripRequest:
    """Tests for CreateTripRequest schema validation."""

    def test_create_trip_valid(self) -> None:
        """Valid request with all required fields succeeds."""
        trip = CreateTripRequest(
            name="Office Commute",
            dest_address="123 Main St, San Francisco, CA",
            dest_lat=37.7749,
            dest_lng=-122.4194,
            arrival_time=datetime.now(timezone.utc) + timedelta(hours=2),
            travel_mode="driving",
            buffer_minutes=15,
            origin_address="456 Oak Ave, San Francisco, CA",
            origin_lat=37.7849,
            origin_lng=-122.4094,
            origin_is_current_location=False,
        )
        assert trip.name == "Office Commute"
        assert trip.dest_lat == 37.7749
        assert trip.dest_lng == -122.4194
        assert trip.travel_mode == "driving"
        assert trip.buffer_minutes == 15
        assert trip.origin_is_current_location is False
        assert trip.is_recurring is False

    def test_create_trip_past_arrival_raises(self) -> None:
        """Past arrival_time raises ValidationError."""
        with pytest.raises(ValidationError, match="arrival_time"):
            CreateTripRequest(
                name="Office Commute",
                dest_address="123 Main St, San Francisco, CA",
                dest_lat=37.7749,
                dest_lng=-122.4194,
                arrival_time=datetime.now(timezone.utc) - timedelta(hours=1),
                origin_address="456 Oak Ave, San Francisco, CA",
                origin_lat=37.7849,
                origin_lng=-122.4094,
            )

    def test_create_trip_origin_required_when_not_current_location(self) -> None:
        """Missing origin fields raises ValidationError when not using current location."""
        with pytest.raises(ValidationError, match="origin"):
            CreateTripRequest(
                name="Office Commute",
                dest_address="123 Main St, San Francisco, CA",
                dest_lat=37.7749,
                dest_lng=-122.4194,
                arrival_time=datetime.now(timezone.utc) + timedelta(hours=2),
                origin_is_current_location=False,
            )

    def test_create_trip_dest_lat_out_of_range(self) -> None:
        """dest_lat=91 raises ValidationError."""
        with pytest.raises(ValidationError, match="dest_lat"):
            CreateTripRequest(
                name="Office Commute",
                dest_address="123 Main St, San Francisco, CA",
                dest_lat=91.0,
                dest_lng=-122.4194,
                arrival_time=datetime.now(timezone.utc) + timedelta(hours=2),
                origin_address="456 Oak Ave, San Francisco, CA",
                origin_lat=37.7849,
                origin_lng=-122.4094,
            )


class TestUpdateUserRequest:
    """Tests for UpdateUserRequest schema validation."""

    def test_update_user_quiet_hours_must_be_paired(self) -> None:
        """Setting quiet_hours_start without quiet_hours_end raises ValidationError."""
        with pytest.raises(ValidationError, match="quiet_hours"):
            UpdateUserRequest(
                quiet_hours_start="22:00",
                quiet_hours_end=None,
            )

    def test_update_user_invalid_buffer(self) -> None:
        """buffer_minutes=7 raises ValidationError."""
        with pytest.raises(ValidationError, match="buffer"):
            UpdateUserRequest(
                default_buffer_minutes=7,
            )
