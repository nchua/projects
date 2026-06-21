"""
Heart-rate ingestion and per-set attribution.

Shared by the workout-create path (Apple Watch live session) and the WHOOP
backfill path. Persists raw samples, attributes each to a set by timestamp
window, and rolls up avg/peak HR onto the Set and WorkoutSession rows.

Zone bucketing (hr_zone_seconds) is supplied by the client/provider:
- WHOOP returns zone durations directly.
- The Apple Watch app computes zones on-device, where it knows the user's
  max HR from HealthKit.
The backend stores whatever it's given rather than guessing max HR here.
"""
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.models.workout import HeartRateSample, Set, WorkoutSession


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize to naive UTC for comparison (DB stores naive UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def ingest_heart_rate(
    db: DBSession,
    session: WorkoutSession,
    samples: Iterable,
    source: str,
) -> int:
    """
    Persist raw HR samples for a session, attribute them to sets by timestamp
    window, and roll up avg/peak HR onto each set and the session.

    `samples` is an iterable of objects with `.timestamp` and `.bpm`
    (e.g. HeartRateSampleCreate). Per-set and session avg/peak that were NOT
    explicitly provided by the client are derived here from the samples.

    Returns the number of samples stored. Caller is responsible for committing.
    """
    # Flatten sets across the session with their (normalized) windows.
    all_sets: List[Set] = [
        s for we in session.workout_exercises for s in we.sets
    ]
    set_windows = [
        (s, _aware(s.start_time), _aware(s.end_time)) for s in all_sets
    ]

    # Accumulate bpm values per set for rollup.
    per_set_bpms: dict[str, List[int]] = {s.id: [] for s in all_sets}
    session_bpms: List[int] = []

    stored = 0
    for sample in samples:
        ts = _aware(sample.timestamp)
        bpm = int(sample.bpm)
        session_bpms.append(bpm)

        matched_set: Optional[Set] = None
        for s, start, end in set_windows:
            if start is not None and end is not None and start <= ts <= end:
                matched_set = s
                break

        db.add(HeartRateSample(
            user_id=session.user_id,
            session_id=session.id,
            set_id=matched_set.id if matched_set else None,
            timestamp=ts,
            bpm=bpm,
            source=source,
        ))
        if matched_set is not None:
            per_set_bpms[matched_set.id].append(bpm)
        stored += 1

    # Roll up per-set avg/peak (don't clobber client-provided values).
    for s in all_sets:
        bpms = per_set_bpms[s.id]
        if not bpms:
            continue
        if s.avg_heart_rate is None:
            s.avg_heart_rate = round(sum(bpms) / len(bpms))
        if s.peak_heart_rate is None:
            s.peak_heart_rate = max(bpms)

    # Roll up session avg/peak (don't clobber client-provided values).
    if session_bpms:
        if session.avg_heart_rate is None:
            session.avg_heart_rate = round(sum(session_bpms) / len(session_bpms))
        if session.peak_heart_rate is None:
            session.peak_heart_rate = max(session_bpms)
        if session.hr_source is None:
            session.hr_source = source

    return stored
