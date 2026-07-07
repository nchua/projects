"""Static per-trip arrival lookup (data/trip_arrivals.json).

NOT a schedule engine: trips are only looked up by trip_id + service date
supplied by the realtime feed, so no calendar / service-day inference ever
happens here. Exists because 511's realtime feeds carry no arrival time for
a trip's terminal stop (StopMonitoring omits arrival-only stops; TripUpdates
only carries the next stop — both verified live 2026-07-01).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "trip_arrivals.json"
PACIFIC = ZoneInfo("America/Los_Angeles")

# Service-day clock arithmetic (SPEC-V2 §4.3): most last trains carry 24:xx+
# GTFS times, so time-of-day comparisons happen in service-day seconds. The
# 3 AM cutover is safe — zero bundled stop events (either agency) fall in
# [03:00, 04:00) or beyond 27:00, verified 2026-07-06. This is arithmetic on
# a timestamp, not calendar inference.
SERVICE_DAY_CUTOVER_S = 3 * 3600
LAST_TRAIN_EPSILON_S = 300

# {trip_id: {stop_code: arrival_seconds_since_midnight}} — may exceed 24h.
_DATA: dict[str, dict[str, int]] = json.loads(DATA_PATH.read_text(encoding="utf-8"))


def service_day_seconds(dt: datetime) -> int:
    """Seconds since PT midnight, mapped into the service day: a clock time
    before the cutover belongs to the previous service day (24:xx+)."""
    local = dt.astimezone(PACIFIC)
    t = local.hour * 3600 + local.minute * 60 + local.second
    return t + 86400 if t < SERVICE_DAY_CUTOVER_S else t


@lru_cache(maxsize=512)
def pair_max_service_s(origin_stop: str, destination_stop: str) -> int | None:
    """Static pair-max (SPEC-V2 §4.2): the latest origin departure time-of-day
    over ALL bundled trips serving origin-before-destination, every day type
    pooled — no calendar lookup. Origin *arrival* seconds stand in for the
    departure (the file stores arrivals only); the badge epsilon absorbs the
    dwell. None when no bundled trip serves the pair."""
    best: int | None = None
    for stops in _DATA.values():
        origin = stops.get(origin_stop)
        destination = stops.get(destination_stop)
        if origin is not None and destination is not None and origin < destination:
            best = origin if best is None else max(best, origin)
    return best


def trip_stops(trip_id: str) -> dict[str, int] | None:
    """Mapping of platform stop codes this trip serves (code → arrival
    seconds), or None if the trip is unknown (e.g. the bundled GTFS revision
    has rotated). Callers use it for membership tests."""
    return _DATA.get(trip_id)


def scheduled_arrival(
    trip_id: str,
    stop_code: str,
    service_date: str | None,
    fallback_date: datetime | None = None,
) -> datetime | None:
    """Scheduled arrival as an aware datetime, or None if unknown.

    service_date is the realtime feed's DataFrameRef ('2026-07-01'); GTFS
    times can exceed 24:00, so anchor at noon − 12h Pacific (DST-safe).
    """
    seconds = _DATA.get(trip_id, {}).get(stop_code)
    if seconds is None:
        return None

    day: date | None = None
    if service_date:
        try:
            day = date.fromisoformat(service_date)
        except ValueError:
            day = None
    if day is None:
        if fallback_date is None:
            return None
        day = fallback_date.astimezone(PACIFIC).date()

    noon = datetime(day.year, day.month, day.day, 12, tzinfo=PACIFIC)
    return noon - timedelta(hours=12) + timedelta(seconds=seconds)
