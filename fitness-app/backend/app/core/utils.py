"""
Core utility functions
"""
from datetime import datetime, date
from typing import Optional, Union


def to_iso8601_utc(dt: Optional[Union[datetime, date]]) -> Optional[str]:
    """
    Convert datetime/date to ISO8601 string.

    For date objects and datetime objects at midnight (00:00:00), returns
    just the date string (YYYY-MM-DD) without time/timezone. This is because
    workout dates are stored as local dates, not UTC timestamps.

    For datetime objects with non-midnight times, appends 'Z' to indicate UTC.

    Args:
        dt: A datetime or date object, or None

    Returns:
        ISO8601 formatted string, or None if input is None

    Examples:
        >>> to_iso8601_utc(datetime(2026, 1, 25, 10, 30, 0))
        '2026-01-25T10:30:00Z'
        >>> to_iso8601_utc(datetime(2026, 1, 25, 0, 0, 0))
        '2026-01-25'
        >>> to_iso8601_utc(date(2026, 1, 25))
        '2026-01-25'
        >>> to_iso8601_utc(None)
        None
    """
    if dt is None:
        return None

    # For date objects (not datetime), just return the date string
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()

    # For datetime objects at midnight, return just the date string
    # This handles workout dates which are stored as local dates, not UTC timestamps
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.date().isoformat()

    # For datetime objects with actual time, append Z to indicate UTC
    return dt.isoformat() + "Z"
