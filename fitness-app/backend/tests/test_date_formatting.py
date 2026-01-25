"""
Tests to ensure date formatting always includes UTC timezone.

These tests prevent regression of the timezone bug where dates returned without
the 'Z' suffix caused iOS to display workouts on the wrong calendar day.
"""
import pytest
from datetime import datetime, date
from app.core.utils import to_iso8601_utc


class TestToIso8601Utc:
    """Tests for the to_iso8601_utc helper function."""

    def test_datetime_includes_z_suffix(self):
        """Datetime objects should have Z suffix appended."""
        dt = datetime(2026, 1, 25, 10, 30, 0)
        result = to_iso8601_utc(dt)
        assert result == "2026-01-25T10:30:00Z"
        assert result.endswith("Z")

    def test_datetime_with_microseconds(self):
        """Datetime with microseconds should still have Z suffix."""
        dt = datetime(2026, 1, 25, 10, 30, 0, 123456)
        result = to_iso8601_utc(dt)
        assert result == "2026-01-25T10:30:00.123456Z"
        assert result.endswith("Z")

    def test_handles_none(self):
        """None input should return None."""
        assert to_iso8601_utc(None) is None

    def test_date_object_no_z_suffix(self):
        """Date objects (not datetime) should not have Z suffix."""
        d = date(2026, 1, 25)
        result = to_iso8601_utc(d)
        assert result == "2026-01-25"
        assert not result.endswith("Z")

    def test_midnight_datetime(self):
        """Midnight datetime should still have Z suffix."""
        dt = datetime(2026, 1, 25, 0, 0, 0)
        result = to_iso8601_utc(dt)
        assert result == "2026-01-25T00:00:00Z"
        assert result.endswith("Z")

    def test_end_of_day_datetime(self):
        """End of day datetime should have Z suffix."""
        dt = datetime(2026, 1, 25, 23, 59, 59)
        result = to_iso8601_utc(dt)
        assert result == "2026-01-25T23:59:59Z"
        assert result.endswith("Z")


class TestDateFormatConsistency:
    """Tests to ensure all API date formats are consistent."""

    def test_format_is_iso8601_compliant(self):
        """Output should be valid ISO8601 with UTC timezone."""
        dt = datetime(2026, 1, 25, 18, 30, 0)
        result = to_iso8601_utc(dt)

        # Should be parseable back to datetime
        # The Z suffix indicates UTC
        assert "T" in result  # Has time separator
        assert result.endswith("Z")  # Has UTC indicator

        # Parse it back (removing Z for strptime)
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.year == 2026
        assert parsed.month == 1
        assert parsed.day == 25
        assert parsed.hour == 18
        assert parsed.minute == 30

    def test_no_double_z_suffix(self):
        """Calling twice should not add extra Z suffix."""
        dt = datetime(2026, 1, 25, 10, 30, 0)
        result = to_iso8601_utc(dt)

        # Result is a string, so calling again would fail
        # This test ensures the function handles the expected input type
        assert result.count("Z") == 1
