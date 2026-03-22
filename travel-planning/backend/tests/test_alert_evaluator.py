"""Exhaustive unit tests for the alert evaluator decision logic."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from app.models.enums import DeliveryStatus, NotificationType
from app.services.alert_evaluator import (
    AlertDecision,
    determine_alert_tier,
    evaluate_decision,
    get_change_direction,
    is_quiet_hours,
    is_significant_change,
    passes_anti_spam,
)


# --- Helpers ---


def _make_trip(
    arrival_time: datetime | None = None,
    buffer_minutes: int = 15,
    last_eta_seconds: int | None = 1800,
    baseline_duration_seconds: int | None = 1500,
) -> MagicMock:
    trip = MagicMock()
    trip.arrival_time = arrival_time or (
        datetime.now(timezone.utc) + timedelta(hours=2)
    )
    trip.buffer_minutes = buffer_minutes
    trip.last_eta_seconds = last_eta_seconds
    trip.baseline_duration_seconds = baseline_duration_seconds
    return trip


def _make_user(
    quiet_start: time | None = None,
    quiet_end: time | None = None,
    tz: str = "America/Los_Angeles",
) -> MagicMock:
    user = MagicMock()
    user.quiet_hours_start = quiet_start
    user.quiet_hours_end = quiet_end
    user.timezone = tz
    return user


def _make_notification(
    tier: NotificationType,
    sent_at: datetime | None = None,
    eta_at_send: int = 1800,
    delivery_status: DeliveryStatus = DeliveryStatus.delivered,
) -> MagicMock:
    n = MagicMock()
    n.type = tier
    n.sent_at = sent_at or datetime.now(timezone.utc) - timedelta(minutes=20)
    n.eta_at_send_seconds = eta_at_send
    n.delivery_status = delivery_status
    return n


# --- determine_alert_tier ---


class TestDetermineAlertTier:
    def test_heads_up_above_60_min(self) -> None:
        assert determine_alert_tier(3700) == NotificationType.heads_up

    def test_prepare_at_30_min(self) -> None:
        assert determine_alert_tier(1800) == NotificationType.prepare

    def test_prepare_at_16_min(self) -> None:
        assert determine_alert_tier(960) == NotificationType.prepare

    def test_leave_soon_at_10_min(self) -> None:
        assert determine_alert_tier(600) == NotificationType.leave_soon

    def test_leave_soon_at_6_min(self) -> None:
        assert determine_alert_tier(360) == NotificationType.leave_soon

    def test_leave_now_at_0(self) -> None:
        assert determine_alert_tier(0) == NotificationType.leave_now

    def test_leave_now_at_negative_3_min(self) -> None:
        assert determine_alert_tier(-180) == NotificationType.leave_now

    def test_running_late_at_negative_6_min(self) -> None:
        assert determine_alert_tier(-360) == NotificationType.running_late

    # Boundary tests
    def test_boundary_exactly_60_min(self) -> None:
        # > 60 min is heads_up, exactly 60 is prepare
        assert determine_alert_tier(3600) == NotificationType.prepare

    def test_boundary_exactly_15_min(self) -> None:
        assert determine_alert_tier(900) == NotificationType.leave_soon

    def test_boundary_exactly_5_min(self) -> None:
        assert determine_alert_tier(300) == NotificationType.leave_now

    def test_boundary_exactly_negative_5_min(self) -> None:
        assert determine_alert_tier(-300) == NotificationType.running_late


# --- is_significant_change ---


class TestIsSignificantChange:
    def test_first_notification_always_significant(self) -> None:
        assert is_significant_change(1800, None, 1500) is True

    def test_below_threshold_not_significant(self) -> None:
        # Baseline 1500s -> threshold = max(300, 150) = 300s
        assert is_significant_change(1800, 1600, 1500) is False  # delta=200

    def test_at_threshold_is_significant(self) -> None:
        assert is_significant_change(1800, 1500, 1500) is True  # delta=300

    def test_above_threshold_significant(self) -> None:
        assert is_significant_change(2200, 1800, 1500) is True  # delta=400

    def test_large_baseline_uses_10_percent(self) -> None:
        # Baseline 6000s -> threshold = max(300, 600) = 600s
        assert is_significant_change(6000, 5500, 6000) is False  # delta=500
        assert is_significant_change(6000, 5300, 6000) is True  # delta=700

    def test_no_baseline_falls_back_to_new_eta(self) -> None:
        # No baseline -> uses new_eta as baseline
        assert is_significant_change(3000, 2600, None) is True  # delta=400, threshold=max(300,300)=300

    def test_symmetric_for_improvements(self) -> None:
        # Abs delta, so improvement is same as worsening
        assert is_significant_change(1500, 1800, 1500) is True  # delta=300


# --- get_change_direction ---


class TestGetChangeDirection:
    def test_initial_when_no_previous(self) -> None:
        assert get_change_direction(1800, None) == "initial"

    def test_worse_when_higher(self) -> None:
        assert get_change_direction(2000, 1800) == "worse"

    def test_better_when_lower(self) -> None:
        assert get_change_direction(1600, 1800) == "better"

    def test_better_when_equal(self) -> None:
        # Equal maps to "better" (not worse)
        assert get_change_direction(1800, 1800) == "better"


# --- passes_anti_spam ---


class TestPassesAntiSpam:
    def test_no_notifications_passes(self) -> None:
        assert passes_anti_spam([], NotificationType.prepare) is True

    def test_max_4_updates_blocks(self) -> None:
        notifs = [
            _make_notification(NotificationType.prepare, sent_at=datetime.now(timezone.utc) - timedelta(minutes=i * 15))
            for i in range(4)
        ]
        assert passes_anti_spam(notifs, NotificationType.prepare) is False

    def test_max_4_updates_does_not_block_leave_now(self) -> None:
        notifs = [
            _make_notification(NotificationType.prepare, sent_at=datetime.now(timezone.utc) - timedelta(minutes=i * 15))
            for i in range(4)
        ]
        # leave_now is exempt from the 4-update limit
        assert passes_anti_spam(notifs, NotificationType.leave_now) is True

    def test_10_min_cooldown_blocks(self) -> None:
        notifs = [
            _make_notification(
                NotificationType.prepare,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
        ]
        assert passes_anti_spam(notifs, NotificationType.prepare) is False

    def test_10_min_cooldown_allows_leave_now(self) -> None:
        notifs = [
            _make_notification(
                NotificationType.prepare,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
        ]
        assert passes_anti_spam(notifs, NotificationType.leave_now) is True

    def test_10_min_cooldown_allows_running_late(self) -> None:
        notifs = [
            _make_notification(
                NotificationType.prepare,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
        ]
        assert passes_anti_spam(notifs, NotificationType.running_late) is True

    def test_cooldown_passed_allows(self) -> None:
        notifs = [
            _make_notification(
                NotificationType.prepare,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=11),
            )
        ]
        assert passes_anti_spam(notifs, NotificationType.prepare) is True

    def test_dismissed_alerts_downgrade_to_silent(self) -> None:
        notifs = [
            _make_notification(
                NotificationType.prepare,
                delivery_status=DeliveryStatus.dismissed,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            ),
            _make_notification(
                NotificationType.prepare,
                delivery_status=DeliveryStatus.dismissed,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            ),
        ]
        result = passes_anti_spam(notifs, NotificationType.prepare)
        assert result == "silent_only"

    def test_dismissed_does_not_affect_leave_now(self) -> None:
        notifs = [
            _make_notification(
                NotificationType.prepare,
                delivery_status=DeliveryStatus.dismissed,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            ),
            _make_notification(
                NotificationType.prepare,
                delivery_status=DeliveryStatus.dismissed,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            ),
        ]
        assert passes_anti_spam(notifs, NotificationType.leave_now) is True


# --- is_quiet_hours ---


class TestIsQuietHours:
    def test_no_quiet_hours_configured(self) -> None:
        user = _make_user()
        assert is_quiet_hours(user) is False

    @freeze_time("2026-03-22T10:00:00-07:00")  # 10 AM PDT
    def test_daytime_not_quiet(self) -> None:
        user = _make_user(quiet_start=time(23, 0), quiet_end=time(7, 0))
        assert is_quiet_hours(user) is False

    @freeze_time("2026-03-22T06:30:00-07:00")  # 6:30 AM PDT
    def test_early_morning_is_quiet(self) -> None:
        user = _make_user(quiet_start=time(23, 0), quiet_end=time(7, 0))
        assert is_quiet_hours(user) is True

    @freeze_time("2026-03-22T23:30:00-07:00")  # 11:30 PM PDT
    def test_late_night_is_quiet(self) -> None:
        user = _make_user(quiet_start=time(23, 0), quiet_end=time(7, 0))
        assert is_quiet_hours(user) is True

    @freeze_time("2026-03-22T14:00:00-07:00")  # 2 PM PDT
    def test_daytime_quiet_hours(self) -> None:
        # Non-overnight: quiet from 13:00 to 15:00
        user = _make_user(quiet_start=time(13, 0), quiet_end=time(15, 0))
        assert is_quiet_hours(user) is True

    @freeze_time("2026-03-22T12:00:00-07:00")  # noon PDT
    def test_outside_daytime_quiet_hours(self) -> None:
        user = _make_user(quiet_start=time(13, 0), quiet_end=time(15, 0))
        assert is_quiet_hours(user) is False


# --- evaluate_decision (full pipeline) ---


class TestEvaluateDecision:
    @freeze_time("2026-03-22T12:00:00Z")
    def test_first_leave_now_always_fires(self) -> None:
        now = datetime.now(timezone.utc)
        # departure = arrival - eta - buffer = now+48 - 30 - 15 = now+3min -> leave_now
        trip = _make_trip(
            arrival_time=now + timedelta(minutes=48),
            last_eta_seconds=1800,
            buffer_minutes=15,
        )
        user = _make_user()

        decision = evaluate_decision(trip, user, 1800, [])
        assert decision.should_send is True
        assert decision.tier == NotificationType.leave_now

    @freeze_time("2026-03-22T12:00:00Z")
    def test_leave_now_not_sent_twice(self) -> None:
        now = datetime.now(timezone.utc)
        # Same setup: departure = now + 3 min -> leave_now
        trip = _make_trip(
            arrival_time=now + timedelta(minutes=48),
            last_eta_seconds=1800,
            buffer_minutes=15,
        )
        user = _make_user()
        existing = [
            _make_notification(NotificationType.leave_now, sent_at=now - timedelta(minutes=2))
        ]

        decision = evaluate_decision(trip, user, 1800, existing)
        assert decision.should_send is False

    @freeze_time("2026-03-22T12:00:00Z")
    def test_running_late_fires_once(self) -> None:
        now = datetime.now(timezone.utc)
        trip = _make_trip(
            arrival_time=now + timedelta(minutes=20),
            last_eta_seconds=1800,  # 30 min ETA but only 20 min to arrival
            buffer_minutes=15,
        )
        user = _make_user()
        # departure was 25 min ago: arrival(+20) - eta(30) - buffer(15) = -25 min
        decision = evaluate_decision(trip, user, 1800, [])

        # time_until_departure = -25 min = -1500s -> running_late
        assert decision.should_send is True
        assert decision.tier == NotificationType.running_late

    @freeze_time("2026-03-22T12:00:00Z")
    def test_heads_up_sent_once_silently(self) -> None:
        now = datetime.now(timezone.utc)
        trip = _make_trip(
            arrival_time=now + timedelta(hours=3),
            last_eta_seconds=1800,
            buffer_minutes=15,
        )
        user = _make_user()

        decision = evaluate_decision(trip, user, 1800, [])
        assert decision.should_send is True
        assert decision.tier == NotificationType.heads_up
        assert decision.silent is True

    @freeze_time("2026-03-22T12:00:00Z")
    def test_prepare_requires_significant_change(self) -> None:
        now = datetime.now(timezone.utc)
        # Set up so time_until_departure = 30 min -> prepare tier
        trip = _make_trip(
            arrival_time=now + timedelta(minutes=30 + 30 + 15),  # depart + eta + buffer
            last_eta_seconds=1800,
            buffer_minutes=15,
            baseline_duration_seconds=1500,
        )
        user = _make_user()
        existing = [
            _make_notification(
                NotificationType.heads_up,
                eta_at_send=1800,
                sent_at=now - timedelta(minutes=30),
            )
        ]

        # Small change (100s < 300s threshold) — should NOT send
        decision = evaluate_decision(trip, user, 1900, existing)
        assert decision.should_send is False
        assert "significance" in decision.reason.lower()

    @freeze_time("2026-03-22T12:00:00Z")
    def test_prepare_sends_on_large_change(self) -> None:
        now = datetime.now(timezone.utc)
        trip = _make_trip(
            arrival_time=now + timedelta(minutes=30 + 30 + 15),
            last_eta_seconds=1800,
            buffer_minutes=15,
            baseline_duration_seconds=1500,
        )
        user = _make_user()
        existing = [
            _make_notification(
                NotificationType.heads_up,
                eta_at_send=1800,
                sent_at=now - timedelta(minutes=30),
            )
        ]

        # Large change (500s > 300s threshold) — should send
        decision = evaluate_decision(trip, user, 2300, existing)
        assert decision.should_send is True
        assert decision.tier == NotificationType.prepare
        assert decision.change_direction == "worse"

    @freeze_time("2026-03-22T12:00:00Z")
    def test_anti_spam_blocks_after_4_updates(self) -> None:
        now = datetime.now(timezone.utc)
        # departure = arrival - eta(3500s~58min) - buffer(15min) = now+30min -> prepare
        trip = _make_trip(
            arrival_time=now + timedelta(minutes=30 + 58 + 15),
            last_eta_seconds=3500,
            buffer_minutes=15,
            baseline_duration_seconds=1500,
        )
        user = _make_user()

        # 4 existing prepare notifications
        existing = [
            _make_notification(
                NotificationType.prepare,
                eta_at_send=1800 + i * 400,
                sent_at=now - timedelta(minutes=(4 - i) * 15),
            )
            for i in range(4)
        ]

        decision = evaluate_decision(trip, user, 3500, existing)
        assert decision.should_send is False
        assert "anti-spam" in decision.reason.lower()

    @freeze_time("2026-03-22T12:00:00Z")
    def test_leave_now_bypasses_anti_spam(self) -> None:
        now = datetime.now(timezone.utc)
        # departure = arrival - eta(1800s=30min) - buffer(15min) = now+48-30-15 = now+3min -> leave_now
        trip = _make_trip(
            arrival_time=now + timedelta(minutes=48),
            last_eta_seconds=1800,
            buffer_minutes=15,
        )
        user = _make_user()

        # 4 existing prepare notifications (anti-spam would block)
        existing = [
            _make_notification(
                NotificationType.prepare,
                sent_at=now - timedelta(minutes=i * 15),
            )
            for i in range(4)
        ]

        # But leave_now bypasses all rules
        decision = evaluate_decision(trip, user, 1800, existing)
        assert decision.should_send is True
        assert decision.tier == NotificationType.leave_now
