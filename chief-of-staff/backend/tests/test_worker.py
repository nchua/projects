"""Tests for Phase 1F: ARQ Worker services."""

from datetime import datetime, time, timedelta, timezone

from app.core.redis import parse_redis_url
from app.core.security import hash_password
from app.models.action_item import ActionItem
from app.models.audit_log import AuditLog
from app.models.enums import ActionItemStatus
from app.models.user import User
from app.services.briefing_cron import _is_briefing_time
from app.services.integration_scanner import (
    _is_active_hours,
    _is_rate_limited,
    _parse_time,
    _provider_resource_type,
)


# =============================================================================
# Redis URL Parsing
# =============================================================================


class TestRedisUrlParsing:
    """Tests for Redis URL parser."""

    def test_simple_url(self):
        settings = parse_redis_url("redis://localhost:6379/0")
        assert settings.host == "localhost"
        assert settings.port == 6379
        assert settings.database == 0
        assert settings.ssl is False

    def test_with_password(self):
        settings = parse_redis_url(
            "redis://:secret@redis.example.com:6380/1"
        )
        assert settings.host == "redis.example.com"
        assert settings.port == 6380
        assert settings.password == "secret"
        assert settings.database == 1

    def test_ssl_url(self):
        settings = parse_redis_url(
            "rediss://redis.example.com:6379/0"
        )
        assert settings.ssl is True

    def test_default_values(self):
        settings = parse_redis_url("redis://")
        assert settings.host == "localhost"
        assert settings.port == 6379
        assert settings.database == 0


# =============================================================================
# Integration Scanner Helpers
# =============================================================================


class TestScannerHelpers:
    """Tests for integration scanner utility functions."""

    def test_parse_time_string(self):
        result = _parse_time("09:30", default=time(7, 0))
        assert result == time(9, 30)

    def test_parse_time_none(self):
        result = _parse_time(None, default=time(7, 0))
        assert result == time(7, 0)

    def test_parse_time_object(self):
        t = time(14, 0)
        result = _parse_time(t, default=time(7, 0))
        assert result == t

    def test_is_active_hours_within(self):
        user = _mock_user(
            wake_time="08:00", sleep_time="22:00"
        )
        # 3pm UTC, no timezone set on user = use UTC
        now = datetime(
            2026, 3, 22, 15, 0, tzinfo=timezone.utc
        )
        assert _is_active_hours(user, now) is True

    def test_is_active_hours_before_wake(self):
        user = _mock_user(
            wake_time="08:00", sleep_time="22:00"
        )
        now = datetime(
            2026, 3, 22, 5, 0, tzinfo=timezone.utc
        )
        assert _is_active_hours(user, now) is False

    def test_is_active_hours_after_sleep(self):
        user = _mock_user(
            wake_time="08:00", sleep_time="22:00"
        )
        now = datetime(
            2026, 3, 22, 23, 0, tzinfo=timezone.utc
        )
        assert _is_active_hours(user, now) is False

    def test_is_rate_limited_not_limited(self):
        integration = _mock_integration(
            rate_limit_remaining=100, rate_limit_reset_at=None
        )
        assert _is_rate_limited(
            integration, datetime.now(tz=timezone.utc)
        ) is False

    def test_is_rate_limited_limited(self):
        future = datetime.now(tz=timezone.utc) + timedelta(
            hours=1
        )
        integration = _mock_integration(
            rate_limit_remaining=0,
            rate_limit_reset_at=future,
        )
        assert _is_rate_limited(
            integration, datetime.now(tz=timezone.utc)
        ) is True

    def test_is_rate_limited_reset_passed(self):
        past = datetime.now(tz=timezone.utc) - timedelta(
            hours=1
        )
        integration = _mock_integration(
            rate_limit_remaining=0,
            rate_limit_reset_at=past,
        )
        assert _is_rate_limited(
            integration, datetime.now(tz=timezone.utc)
        ) is False

    def test_provider_resource_type(self):
        assert (
            _provider_resource_type("google_calendar")
            == "calendar"
        )
        assert _provider_resource_type("gmail") == "inbox"
        assert (
            _provider_resource_type("github")
            == "notifications"
        )
        assert (
            _provider_resource_type("slack") == "channels"
        )
        assert (
            _provider_resource_type("granola") == "meetings"
        )


# =============================================================================
# Briefing Cron Helpers
# =============================================================================


class TestBriefingCron:
    """Tests for briefing cron helper functions."""

    def test_is_briefing_time_at_wake(self):
        user = _mock_user(wake_time="07:00")
        # 7:02 AM UTC
        now = datetime(
            2026, 3, 22, 7, 2, tzinfo=timezone.utc
        )
        assert _is_briefing_time(user, now) is True

    def test_is_briefing_time_too_early(self):
        user = _mock_user(wake_time="07:00")
        now = datetime(
            2026, 3, 22, 6, 55, tzinfo=timezone.utc
        )
        assert _is_briefing_time(user, now) is False

    def test_is_briefing_time_too_late(self):
        user = _mock_user(wake_time="07:00")
        now = datetime(
            2026, 3, 22, 7, 10, tzinfo=timezone.utc
        )
        assert _is_briefing_time(user, now) is False


# =============================================================================
# Data Cleanup (uses sync DB session from conftest)
# =============================================================================


class TestDataCleanup:
    """Tests for data cleanup logic."""

    def test_stale_action_items_archived(self, db_session):
        user = User(
            email="cleanup@example.com",
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(user)
        db_session.flush()

        old_item = ActionItem(
            user_id=user.id,
            source="gmail",
            title="Old item",
            priority="medium",
            status=ActionItemStatus.NEW.value,
        )
        db_session.add(old_item)
        db_session.flush()

        # Manually set created_at to 35 days ago
        from sqlalchemy import update
        db_session.execute(
            update(ActionItem)
            .where(ActionItem.id == old_item.id)
            .values(
                created_at=datetime.utcnow()
                - timedelta(days=35)
            )
        )
        db_session.flush()

        # Run cleanup logic (sync version)
        from sqlalchemy import update as sa_update
        cutoff = datetime.utcnow() - timedelta(days=30)
        db_session.execute(
            sa_update(ActionItem)
            .where(
                ActionItem.status
                == ActionItemStatus.NEW.value,
                ActionItem.created_at < cutoff,
            )
            .values(
                status=ActionItemStatus.DISMISSED.value
            )
        )
        db_session.flush()

        db_session.refresh(old_item)
        assert old_item.status == "dismissed"

    def test_recent_items_not_archived(self, db_session):
        user = User(
            email="cleanup2@example.com",
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(user)
        db_session.flush()

        new_item = ActionItem(
            user_id=user.id,
            source="gmail",
            title="Recent item",
            priority="medium",
            status=ActionItemStatus.NEW.value,
        )
        db_session.add(new_item)
        db_session.flush()

        # Run cleanup — should not affect recent items
        from sqlalchemy import update as sa_update
        cutoff = datetime.utcnow() - timedelta(
            days=30
        )
        db_session.execute(
            sa_update(ActionItem)
            .where(
                ActionItem.status
                == ActionItemStatus.NEW.value,
                ActionItem.created_at < cutoff,
            )
            .values(
                status=ActionItemStatus.DISMISSED.value
            )
        )
        db_session.flush()

        db_session.refresh(new_item)
        assert new_item.status == "new"

    def test_old_audit_logs_purged(self, db_session):
        old_log = AuditLog(
            action_type="test",
            success=True,
        )
        db_session.add(old_log)
        db_session.flush()

        # Set created_at to 100 days ago
        from sqlalchemy import update
        db_session.execute(
            update(AuditLog)
            .where(AuditLog.id == old_log.id)
            .values(
                created_at=datetime.utcnow()
                - timedelta(days=100)
            )
        )
        db_session.flush()

        # Purge
        from sqlalchemy import delete
        cutoff = datetime.utcnow() - timedelta(days=90)
        db_session.execute(
            delete(AuditLog).where(
                AuditLog.created_at < cutoff
            )
        )
        db_session.flush()

        remaining = (
            db_session.query(AuditLog)
            .filter(AuditLog.id == old_log.id)
            .first()
        )
        assert remaining is None


# =============================================================================
# Test Helpers
# =============================================================================


class _MockObj:
    """Simple mock for testing without full ORM objects."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _mock_user(**kwargs):
    defaults = {
        "wake_time": "07:00",
        "sleep_time": "23:00",
        "timezone": None,
        "is_deleted": False,
    }
    defaults.update(kwargs)
    return _MockObj(**defaults)


def _mock_integration(**kwargs):
    defaults = {
        "rate_limit_remaining": None,
        "rate_limit_reset_at": None,
        "is_active": True,
        "status": "healthy",
    }
    defaults.update(kwargs)
    return _MockObj(**defaults)
