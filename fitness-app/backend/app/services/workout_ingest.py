"""
Small ingest-time helpers shared by POST /workouts and POST /sync.
"""
from typing import Optional, Tuple


def resolve_duration_fields(
    duration_minutes: Optional[int], duration_seconds: Optional[int]
) -> Tuple[Optional[int], Optional[int]]:
    """Persist both duration columns from whichever the client sent.

    ``duration_seconds`` is the exact length (ARISE v3 §7.5); when the client
    sends only seconds, minutes are derived (never 0 for a non-zero length).
    """
    if duration_minutes is None and duration_seconds:
        duration_minutes = max(1, round(duration_seconds / 60))
    return duration_minutes, duration_seconds
