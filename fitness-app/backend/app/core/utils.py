"""
Core utility functions
"""
from datetime import date, datetime, timezone
from typing import Optional, Union


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware UTC.

    SQLite returns naive datetimes; PostgreSQL returns aware ones.
    This helper normalizes both to aware UTC so comparisons are safe.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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


def derive_local_date(dt: Optional[datetime]) -> Optional[date]:
    """Best-effort local calendar day for a session datetime.

    Companion to ``WorkoutSession.local_date`` for writes where the client
    didn't send an explicit local day. A midnight-stored datetime means
    "this local calendar day" (manual and screenshot logs — the same
    convention ``to_iso8601_utc`` serializes), so its date part IS the local
    day. A non-midnight value is a real UTC instant whose local day depends
    on a timezone we don't know here — return None and let readers fall
    back to shifting by the requesting client's tz offset.
    """
    if dt is None:
        return None
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.date()
    return None
