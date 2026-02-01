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
"""
import pytest
from datetime import datetime, date, timezone, timedelta
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
        Midnight datetime should return date-only string.
        This is the KEY FIX for the timezone bug.

        Workout dates are stored as midnight datetime but represent LOCAL dates,
        not UTC timestamps. Returning "2026-02-01" instead of "2026-02-01T00:00:00Z"
        prevents iOS from incorrectly converting UTC midnight to local time.
        """
        dt = datetime(2026, 2, 1, 0, 0, 0)
        result = to_iso8601_utc(dt)
        assert result == "2026-02-01"
        assert "T" not in result
        assert "Z" not in result

    def test_midnight_with_zero_microseconds(self):
        """Midnight with explicit zero microseconds should still be date-only."""
        dt = datetime(2026, 2, 1, 0, 0, 0, 0)
        result = to_iso8601_utc(dt)
        assert result == "2026-02-01"

    # === Actual timestamps (created_at, updated_at, etc.) ===

    def test_datetime_with_time_includes_z_suffix(self):
        """Non-midnight datetime should have Z suffix (actual UTC timestamp)."""
        dt = datetime(2026, 1, 25, 10, 30, 0)
        result = to_iso8601_utc(dt)
        assert result == "2026-01-25T10:30:00Z"
        assert result.endswith("Z")

    def test_datetime_with_microseconds(self):
        """Datetime with non-zero time components should have Z suffix."""
        dt = datetime(2026, 1, 25, 10, 30, 0, 123456)
        result = to_iso8601_utc(dt)
        assert result == "2026-01-25T10:30:00.123456Z"
        assert result.endswith("Z")

    def test_end_of_day_datetime(self):
        """End of day (23:59:59) should have Z suffix."""
        dt = datetime(2026, 1, 25, 23, 59, 59)
        result = to_iso8601_utc(dt)
        assert result == "2026-01-25T23:59:59Z"
        assert result.endswith("Z")

    def test_one_second_past_midnight(self):
        """00:00:01 should have Z suffix (not midnight)."""
        dt = datetime(2026, 2, 1, 0, 0, 1)
        result = to_iso8601_utc(dt)
        assert result == "2026-02-01T00:00:01Z"
        assert result.endswith("Z")

    def test_one_microsecond_past_midnight(self):
        """00:00:00.000001 should have Z suffix (not exact midnight)."""
        dt = datetime(2026, 2, 1, 0, 0, 0, 1)
        result = to_iso8601_utc(dt)
        assert result == "2026-02-01T00:00:00.000001Z"
        assert result.endswith("Z")

    # === Edge cases ===

    def test_handles_none(self):
        """None input should return None."""
        assert to_iso8601_utc(None) is None

    def test_year_boundary(self):
        """New Year's midnight should return date-only."""
        dt = datetime(2027, 1, 1, 0, 0, 0)
        result = to_iso8601_utc(dt)
        assert result == "2027-01-01"

    def test_leap_year_date(self):
        """Feb 29 on leap year should work correctly."""
        dt = datetime(2028, 2, 29, 0, 0, 0)  # 2028 is a leap year
        result = to_iso8601_utc(dt)
        assert result == "2028-02-29"


class TestDateRoundTrip:
    """
    Tests that simulate the full date flow:
    iOS -> Backend -> Database -> Backend -> iOS
    """

    def test_workout_date_roundtrip(self):
        """
        Simulate: User logs workout on Feb 1 local time.

        1. iOS sends "2026-02-01"
        2. Backend parses to datetime(2026, 2, 1, 0, 0, 0)
        3. Backend returns "2026-02-01" (no Z!)
        4. iOS should display as Feb 1 (not Jan 31)
        """
        # Step 1: iOS sends date string
        ios_date_string = "2026-02-01"

        # Step 2: Backend parses (simulating workout schema)
        backend_datetime = datetime.strptime(ios_date_string, "%Y-%m-%d")
        assert backend_datetime == datetime(2026, 2, 1, 0, 0, 0)

        # Step 3: Backend returns via to_iso8601_utc
        api_response = to_iso8601_utc(backend_datetime)

        # Step 4: Verify format is date-only (no timezone shift on iOS)
        assert api_response == "2026-02-01"
        assert "T" not in api_response
        assert "Z" not in api_response

    def test_timestamp_roundtrip(self):
        """
        Simulate: created_at timestamp (actual UTC time).

        1. Backend creates datetime.utcnow()
        2. Backend returns with Z suffix
        3. iOS correctly interprets as UTC
        """
        # Step 1: Backend creates UTC timestamp
        created_at = datetime(2026, 2, 1, 21, 58, 30)  # 9:58 PM UTC

        # Step 2: Backend returns via to_iso8601_utc
        api_response = to_iso8601_utc(created_at)

        # Step 3: Verify format has Z suffix
        assert api_response == "2026-02-01T21:58:30Z"
        assert api_response.endswith("Z")


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

    def test_workout_date_extraction(self):
        """
        Workout dates stored as datetime should extract to date correctly.
        """
        # Workout date stored as midnight datetime
        workout_datetime = datetime(2026, 2, 1, 0, 0, 0)

        # Extract date part (how quest service does it)
        workout_date = workout_datetime.date() if hasattr(workout_datetime, 'date') else workout_datetime

        assert workout_date == date(2026, 2, 1)

    def test_date_comparison_same_day(self):
        """Dates on same day should match."""
        try:
            from app.services.quest_service import get_today_utc
        except ImportError:
            pytest.skip("quest_service dependencies not available")

        # Simulate a workout from "today"
        today = get_today_utc()
        workout_datetime = datetime(today.year, today.month, today.day, 0, 0, 0)
        workout_date = workout_datetime.date()

        assert workout_date == today


class TestTimezoneScenarios:
    """
    Tests for specific timezone scenarios that have caused bugs.
    """

    def test_pst_user_feb1_workout(self):
        """
        Scenario: User in PST (UTC-8) logs workout at 1:58 PM on Feb 1.

        Local time: Feb 1, 1:58 PM PST
        UTC time: Feb 1, 9:58 PM UTC

        The workout should display as Feb 1 everywhere.
        """
        # User selects Feb 1 in their local timezone
        local_date_string = "2026-02-01"

        # Backend stores as midnight datetime
        stored_datetime = datetime.strptime(local_date_string, "%Y-%m-%d")

        # Backend returns date-only string
        returned = to_iso8601_utc(stored_datetime)

        # Should NOT have timezone info that would cause shift
        assert returned == "2026-02-01"
        assert "Z" not in returned

    def test_late_night_workout_same_day(self):
        """
        Scenario: User logs workout at 11 PM local time.

        Even though it might be the next day in UTC, the workout
        date should reflect when the user actually worked out.
        """
        # User worked out on Jan 31 at 11 PM PST
        # (That's Feb 1 7 AM UTC, but the workout is "Jan 31")
        local_date_string = "2026-01-31"

        stored_datetime = datetime.strptime(local_date_string, "%Y-%m-%d")
        returned = to_iso8601_utc(stored_datetime)

        assert returned == "2026-01-31"

    def test_old_buggy_format_would_fail(self):
        """
        Verify that the OLD format would cause problems.

        Old: "2026-02-01T00:00:00Z" (midnight UTC)
        In PST: 4:00 PM on Jan 31 (WRONG DAY!)

        This test documents the bug we fixed.
        """
        # The OLD buggy format
        buggy_format = "2026-02-01T00:00:00Z"

        # If iOS parses this as UTC and converts to PST (UTC-8):
        # Midnight UTC = 4 PM previous day in PST
        utc_datetime = datetime.fromisoformat(buggy_format.replace("Z", "+00:00"))
        pst_offset = timedelta(hours=-8)
        pst_datetime = utc_datetime + pst_offset

        # The displayed date would be JANUARY 31, not February 1!
        assert pst_datetime.day == 31  # Wrong!
        assert pst_datetime.month == 1  # Wrong!

        # Our fix returns "2026-02-01" which doesn't get converted
        correct_format = to_iso8601_utc(datetime(2026, 2, 1, 0, 0, 0))
        assert correct_format == "2026-02-01"  # No timezone = no conversion


class TestWorkoutSchemaDateParsing:
    """Tests for workout date parsing in the schema."""

    def test_parse_date_only_string(self):
        """Date-only string should parse to midnight datetime."""
        # Note: This tests the parsing logic without importing the schema
        # The schema uses datetime.strptime(v, "%Y-%m-%d") for date-only strings

        # This is what iOS sends
        date_string = "2026-02-01"
        parsed = datetime.strptime(date_string, "%Y-%m-%d")

        assert parsed == datetime(2026, 2, 1, 0, 0, 0)
        assert parsed.hour == 0
        assert parsed.minute == 0
        assert parsed.second == 0

    def test_date_string_format_consistency(self):
        """All date-only strings should use YYYY-MM-DD format."""
        test_dates = [
            ("2026-01-01", datetime(2026, 1, 1)),
            ("2026-12-31", datetime(2026, 12, 31)),
            ("2028-02-29", datetime(2028, 2, 29)),  # Leap year
        ]

        for date_str, expected_dt in test_dates:
            parsed = datetime.strptime(date_str, "%Y-%m-%d")
            assert parsed == expected_dt

            # Round trip through our formatter
            formatted = to_iso8601_utc(parsed)
            assert formatted == date_str


# Run with: pytest tests/test_date_formatting.py -v
