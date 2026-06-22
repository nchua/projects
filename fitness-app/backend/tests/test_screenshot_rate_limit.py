"""
Unit tests for screenshot processing rate limiting.

Tests the _check_screenshot_rate_limit function directly since full
screenshot endpoint testing would require mocking the Claude Vision API.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.screenshot import (
    _check_screenshot_rate_limit,
)
from app.models.screenshot_usage import ScreenshotUsage

# Pin the clock for the daily-window tests. The daily cap counts usages with
# created_at >= UTC-midnight-today; spreading test usages over "now - N minutes"
# straddles the midnight boundary and drops some out of the window when the
# suite runs in the ~20 min after 00:00 UTC, making the at-limit test flaky.
# Freezing "now" to a fixed mid-day instant keeps every usage inside one UTC day.
FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDateTime(datetime):
    """datetime subclass whose now() is fixed — preserves replace()/arithmetic."""

    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW if tz is not None else FIXED_NOW.replace(tzinfo=None)


class TestScreenshotRateLimit:
    """Tests for _check_screenshot_rate_limit function."""

    @patch("app.api.screenshot.datetime", _FrozenDateTime)
    def test_rate_limit_allows_under_daily_limit(self, db, create_test_user):
        """19 usages recorded, next request passes."""
        user, _ = create_test_user(email="underrl@example.com")

        # Record 19 usages (under the 20 limit), spread out to avoid cooldown
        for i in range(19):
            usage = ScreenshotUsage(
                user_id=user.id,
                screenshots_count=1,
                created_at=FIXED_NOW - timedelta(minutes=i + 1),
            )
            db.add(usage)
        db.commit()

        # Should not raise — still under the limit
        _check_screenshot_rate_limit(db, user.id, screenshot_count=1)

    @patch("app.api.screenshot.datetime", _FrozenDateTime)
    def test_rate_limit_blocks_at_daily_limit(self, db, create_test_user):
        """20 usages recorded, raises HTTPException 429."""
        user, _ = create_test_user(email="overrl@example.com")

        # Record 20 usages (at the limit), spread out to avoid cooldown
        for i in range(20):
            usage = ScreenshotUsage(
                user_id=user.id,
                screenshots_count=1,
                created_at=FIXED_NOW - timedelta(minutes=i + 1),
            )
            db.add(usage)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            _check_screenshot_rate_limit(db, user.id, screenshot_count=1)
        assert exc_info.value.status_code == 429
        assert "daily limit" in exc_info.value.detail.lower()

    def test_rate_limit_cooldown_enforced(self, db, create_test_user):
        """Usage within 10 seconds raises HTTPException 429."""
        user, _ = create_test_user(email="cooldown@example.com")

        # Record a usage just now (within cooldown)
        usage = ScreenshotUsage(
            user_id=user.id,
            screenshots_count=1,
            created_at=datetime.now(timezone.utc),
        )
        db.add(usage)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            _check_screenshot_rate_limit(db, user.id, screenshot_count=1)
        assert exc_info.value.status_code == 429
        assert "wait" in exc_info.value.detail.lower()

    @patch("app.api.screenshot.settings")
    def test_rate_limit_kill_switch(self, mock_settings, db, create_test_user):
        """SCREENSHOT_PROCESSING_ENABLED=False raises 503."""
        user, _ = create_test_user(email="killswitch@example.com")
        mock_settings.SCREENSHOT_PROCESSING_ENABLED = False

        with pytest.raises(HTTPException) as exc_info:
            _check_screenshot_rate_limit(db, user.id, screenshot_count=1)
        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.detail.lower()
