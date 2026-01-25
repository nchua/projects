"""
Core utility functions
"""
from datetime import datetime, date
from typing import Optional, Union


def to_iso8601_utc(dt: Optional[Union[datetime, date]]) -> Optional[str]:
    """
    Convert datetime/date to ISO8601 string with explicit UTC timezone.

    This function ensures all dates returned to clients have the 'Z' suffix
    to indicate UTC timezone, preventing timezone parsing issues on iOS.

    Args:
        dt: A datetime or date object, or None

    Returns:
        ISO8601 formatted string with 'Z' suffix, or None if input is None

    Examples:
        >>> to_iso8601_utc(datetime(2026, 1, 25, 10, 30, 0))
        '2026-01-25T10:30:00Z'
        >>> to_iso8601_utc(date(2026, 1, 25))
        '2026-01-25'
        >>> to_iso8601_utc(None)
        None
    """
    if dt is None:
        return None

    # For date objects (not datetime), just return the date string without Z
    # Date-only strings don't have timezone context
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()

    # For datetime objects, append Z to indicate UTC
    return dt.isoformat() + "Z"
