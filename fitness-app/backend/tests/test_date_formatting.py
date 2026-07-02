"""
Tests for date handling across the fitness app.

THE DATE CONTRACT:
==================
1. Workout dates are LOCAL DATES (the day the user worked out in their timezone)
2. iOS sends dates as "YYYY-MM-DD" strings (local date, no time)
3. Backend stores as datetime at midnight (naive, represents local date)
4. Backend returns date-only strings "YYYY-MM-DD" for workout dates (no 'Z' suffix)
5. iOS parses date-only strings using LOCAL timezone
6. Quest service compares dates using UTC calendar day

This contract ensures:
- A workout logged on "Feb 1" in PST displays as "Feb 1" everywhere
- Quests use UTC for daily reset (midnight UTC = new quest day)

The full iOS -> backend -> iOS round trip (the real parse_date validator plus
to_iso8601_utc through the workout endpoints) is covered in
test_workouts_crud.py::TestWorkoutDateRoundTrip.
"""
from datetime import date, datetime

import pytest

from app.core.utils import to_iso8601_utc


class TestToIso8601Utc:
    """Tests for the to_iso8601_utc helper function."""

    # === Date-only values (workout dates) ===

    def test_date_object_returns_date_string(self):
        """Date objects should return YYYY-MM-DD without time or Z."""
        d = date(2026, 2, 1)
        result = to_iso8601_utc(d)
        assert result == "2026-02-01"
        assert "T" not in result
        assert "Z" not in result

    def test_midnight_datetime_returns_date_string(self):
        """
        Midnight datetime (with or without explicit zero microseconds) should
        return date-only string. This is the KEY FIX for the timezone bug.

        Workout dates are stored as midnight datetime but represent LOCAL dates,
        not UTC timestamps. Returning "2026-02-01" instead of "2026-02-01T00:00:00Z"
        prevents iOS from incorrectly converting UTC midnight to local time.

        The OLD buggy format returned "2026-02-01T00:00:00Z" (midnight UTC).
        iOS parsed that as a UTC instant and converted it to local time — in
        PST (UTC-8) midnight UTC is 4:00 PM the PREVIOUS day, so a Feb 1
        workout displayed as January 31 (wrong day!). Late-night workouts hit
        the same shift. A date-only string carries no timezone, so iOS has
        nothing to convert and the day the user picked is the day displayed.
        """
        for dt in [datetime(2026, 2, 1, 0, 0, 0), datetime(2026, 2, 1, 0, 0, 0, 0)]:
            result = to_iso8601_utc(dt)
            assert result == "2026-02-01"
            assert "T" not in result
            assert "Z" not in result

    # === Actual timestamps (created_at, updated_at, etc.) ===

    @pytest.mark.parametrize(
        "dt,expected",
        [
            pytest.param(
                datetime(2026, 1, 25, 10, 30, 0), "2026-01-25T10:30:00Z",
                id="with_time",
            ),
            pytest.param(
                datetime(2026, 1, 25, 10, 30, 0, 123456), "2026-01-25T10:30:00.123456Z",
                id="microseconds",
            ),
            pytest.param(
                datetime(2026, 1, 25, 23, 59, 59), "2026-01-25T23:59:59Z",
                id="end_of_day",
            ),
            pytest.param(
                datetime(2026, 2, 1, 0, 0, 1), "2026-02-01T00:00:01Z",
                id="one_second_past_midnight",
            ),
            pytest.param(
                datetime(2026, 2, 1, 0, 0, 0, 1), "2026-02-01T00:00:00.000001Z",
                id="one_microsecond_past_midnight",
            ),
        ],
    )
    def test_non_midnight_datetime_includes_z_suffix(self, dt, expected):
        """Any datetime with non-zero time components is an actual UTC
        timestamp and must keep its time with a Z suffix."""
        result = to_iso8601_utc(dt)
        assert result == expected
        assert result.endswith("Z")

    # === Edge cases ===

    def test_handles_none(self):
        """None input should return None."""
        assert to_iso8601_utc(None) is None


class TestQuestDateMatching:
    """
    Tests for quest date matching logic.

    Quests use UTC dates for daily reset, but workout dates are local dates.
    This can cause mismatches if not handled correctly.
    """

    def test_get_today_utc_returns_date_object(self):
        """get_today_utc should return a date, not datetime."""
        try:
            from app.services.quest_service import get_today_utc
        except ImportError:
            pytest.skip("quest_service dependencies not available")

        today = get_today_utc()
        assert isinstance(today, date)
        assert not isinstance(today, datetime)


# Run with: pytest tests/test_date_formatting.py -v
