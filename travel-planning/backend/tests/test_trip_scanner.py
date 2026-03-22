"""Unit tests for trip scanner — phase detection and polling logic."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import datetime, timedelta, timezone

from freezegun import freeze_time

from app.models.enums import MonitoringPhase
from app.services.trip_scanner import (
    determine_phase,
    estimate_rough_eta_seconds,
    should_check_now,
)
from app.services.utils import haversine


# --- haversine ---


class TestHaversine:
    def test_same_point_is_zero(self) -> None:
        assert haversine(37.7749, -122.4194, 37.7749, -122.4194) == 0.0

    def test_sf_to_sj(self) -> None:
        # SF to San Jose ~70 km
        dist = haversine(37.7749, -122.4194, 37.3382, -121.8863)
        assert 60 < dist < 80

    def test_symmetrical(self) -> None:
        d1 = haversine(37.7749, -122.4194, 34.0522, -118.2437)
        d2 = haversine(34.0522, -118.2437, 37.7749, -122.4194)
        assert abs(d1 - d2) < 0.01


# --- determine_phase ---


class TestDeterminePhase:
    """Test phase detection at various time-until-notify values."""

    def _make_arrival(
        self,
        now: datetime,
        eta_seconds: int,
        buffer_minutes: int,
        time_until_notify_minutes: float,
    ) -> datetime:
        """Calculate an arrival_time that produces the desired time_until_notify."""
        # notify_at = arrival - eta - buffer
        # time_until_notify = notify_at - now
        # arrival = notify_at + eta + buffer
        # arrival = now + time_until_notify + eta + buffer
        return (
            now
            + timedelta(minutes=time_until_notify_minutes)
            + timedelta(seconds=eta_seconds)
            + timedelta(minutes=buffer_minutes)
        )

    @freeze_time("2026-03-22T12:00:00Z")
    def test_dormant_at_4_hours(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, 240)  # 4 hours until notify
        phase = determine_phase(arrival, 1800, 15, now)
        assert phase == MonitoringPhase.dormant

    @freeze_time("2026-03-22T12:00:00Z")
    def test_passive_at_2_hours(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, 120)  # 2 hours until notify
        phase = determine_phase(arrival, 1800, 15, now)
        assert phase == MonitoringPhase.passive

    @freeze_time("2026-03-22T12:00:00Z")
    def test_active_at_30_min(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, 30)  # 30 min until notify
        phase = determine_phase(arrival, 1800, 15, now)
        assert phase == MonitoringPhase.active

    @freeze_time("2026-03-22T12:00:00Z")
    def test_critical_at_10_min(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, 10)  # 10 min until notify
        phase = determine_phase(arrival, 1800, 15, now)
        assert phase == MonitoringPhase.critical

    @freeze_time("2026-03-22T12:00:00Z")
    def test_departed_past_notify(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, -5)  # 5 min past notify
        phase = determine_phase(arrival, 1800, 15, now)
        assert phase == MonitoringPhase.departed

    @freeze_time("2026-03-22T12:00:00Z")
    def test_boundary_exactly_3_hours(self) -> None:
        now = datetime.now(timezone.utc)
        # Exactly 3 hours -> should be passive (> 3h is dormant, <= 3h is passive)
        arrival = self._make_arrival(now, 1800, 15, 180)  # exactly 3 hours
        phase = determine_phase(arrival, 1800, 15, now)
        # 180 min = 3 hours = 10800s, > 10800 is dormant, so exactly 180 is passive
        assert phase == MonitoringPhase.passive

    @freeze_time("2026-03-22T12:00:00Z")
    def test_boundary_exactly_1_hour(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, 60)
        phase = determine_phase(arrival, 1800, 15, now)
        # 60 min = 3600s, > 3600 is passive, so exactly 60 is active
        assert phase == MonitoringPhase.active

    @freeze_time("2026-03-22T12:00:00Z")
    def test_boundary_exactly_15_min(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, 15)
        phase = determine_phase(arrival, 1800, 15, now)
        # 15 min = 900s, > 900 is active, so exactly 15 is critical
        assert phase == MonitoringPhase.critical

    @freeze_time("2026-03-22T12:00:00Z")
    def test_boundary_exactly_0(self) -> None:
        now = datetime.now(timezone.utc)
        arrival = self._make_arrival(now, 1800, 15, 0)
        phase = determine_phase(arrival, 1800, 15, now)
        # 0 seconds, > 0 is critical, so exactly 0 is departed
        assert phase == MonitoringPhase.departed

    @freeze_time("2026-03-22T12:00:00Z")
    def test_no_eta_defaults_to_1_hour(self) -> None:
        """When last_eta_seconds is None, assume 1 hour default."""
        now = datetime.now(timezone.utc)
        # arrival in 2.5 hours, no ETA, buffer 15 min
        # estimated_notify_at = arrival - 1h (default) = now + 1.5h
        # time_until_notify = 1.5h = 5400s -> passive
        arrival = now + timedelta(hours=2, minutes=30)
        phase = determine_phase(arrival, None, 15, now)
        assert phase == MonitoringPhase.passive


# --- should_check_now ---


class TestShouldCheckNow:
    @freeze_time("2026-03-22T12:00:00Z")
    def test_dormant_never_checks(self) -> None:
        now = datetime.now(timezone.utc)
        assert should_check_now(MonitoringPhase.dormant, None, now) is False

    @freeze_time("2026-03-22T12:00:00Z")
    def test_departed_never_checks(self) -> None:
        now = datetime.now(timezone.utc)
        assert should_check_now(MonitoringPhase.departed, None, now) is False

    @freeze_time("2026-03-22T12:00:00Z")
    def test_never_checked_always_true(self) -> None:
        now = datetime.now(timezone.utc)
        assert should_check_now(MonitoringPhase.passive, None, now) is True
        assert should_check_now(MonitoringPhase.active, None, now) is True
        assert should_check_now(MonitoringPhase.critical, None, now) is True

    @freeze_time("2026-03-22T12:00:00Z")
    def test_passive_15_min_interval(self) -> None:
        now = datetime.now(timezone.utc)
        # Checked 14 min ago -> don't check yet
        checked_14m = now - timedelta(minutes=14)
        assert should_check_now(MonitoringPhase.passive, checked_14m, now) is False

        # Checked 15 min ago -> check now
        checked_15m = now - timedelta(minutes=15)
        assert should_check_now(MonitoringPhase.passive, checked_15m, now) is True

    @freeze_time("2026-03-22T12:00:00Z")
    def test_active_5_min_interval(self) -> None:
        now = datetime.now(timezone.utc)
        checked_4m = now - timedelta(minutes=4)
        assert should_check_now(MonitoringPhase.active, checked_4m, now) is False

        checked_5m = now - timedelta(minutes=5)
        assert should_check_now(MonitoringPhase.active, checked_5m, now) is True

    @freeze_time("2026-03-22T12:00:00Z")
    def test_critical_2_min_interval(self) -> None:
        now = datetime.now(timezone.utc)
        checked_1m = now - timedelta(minutes=1, seconds=59)
        assert should_check_now(MonitoringPhase.critical, checked_1m, now) is False

        checked_2m = now - timedelta(minutes=2)
        assert should_check_now(MonitoringPhase.critical, checked_2m, now) is True


# --- estimate_rough_eta_seconds ---


class TestEstimateRoughEta:
    def test_sf_to_sj(self) -> None:
        # ~70 km at 40 km/h = ~1.75 hours = ~6300 seconds
        eta = estimate_rough_eta_seconds(37.7749, -122.4194, 37.3382, -121.8863)
        assert 5000 < eta < 8000

    def test_same_location_is_zero(self) -> None:
        eta = estimate_rough_eta_seconds(37.7749, -122.4194, 37.7749, -122.4194)
        assert eta == 0
