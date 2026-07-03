"""BART GTFS-Realtime upstream client (SPEC-BART §6.2).

No API key and no published rate limit — the guard here is a runaway-bug
backstop, not a budget (worst continuous case is ~132 calls/hr at the chosen
TTLs). Protobuf is parsed immediately at fetch time into plain dicts and the
*parsed* form is cached, so pure pair logic never sees protobuf objects and
a DecodeError counts as a fetch failure (→ serve stale).

Both endpoints 301/307-redirect; the shared client follows redirects.
"""

from __future__ import annotations

from datetime import datetime

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from app.upstream import Upstream

BASE_URL = "https://api.bart.gov/gtfsrt"

TRIP_UPDATES_TTL_S = 30
ALERTS_TTL_S = 300
GUARD_MAX_CALLS_PER_HOUR = 150
UPSTREAM_TIMEOUT_S = 10

_upstream = Upstream(
    guard_max_calls_per_hour=GUARD_MAX_CALLS_PER_HOUR,
    timeout_s=UPSTREAM_TIMEOUT_S,
    follow_redirects=True,  # both BART endpoints redirect (verified — §1.3)
)

_CANCELED = gtfs_realtime_pb2.TripDescriptor.CANCELED
_STU_SKIPPED = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED


def _event(stu, name: str) -> dict | None:
    """StopTimeEvent → {'time': epoch|None, 'delay': s|None}, or None if absent."""
    if not stu.HasField(name):
        return None
    event = getattr(stu, name)
    return {
        "time": event.time if event.HasField("time") else None,
        "delay": event.delay if event.HasField("delay") else None,
    }


def parse_trip_updates(raw: bytes) -> dict:
    """Protobuf bytes → {'trips': [{'trip_id', 'stops': [...]}]}.

    CANCELED trips and SKIPPED stops are dropped here (SPEC-BART §5.3);
    everything downstream can assume the trains listed actually run.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(raw)
    except DecodeError as exc:  # count as fetch failure → serve stale
        raise ValueError(f"undecodable GTFS-RT feed: {exc}") from exc

    trips = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        if update.trip.schedule_relationship == _CANCELED:
            continue
        stops = [
            {
                "stop_id": stu.stop_id,
                "arrival": _event(stu, "arrival"),
                "departure": _event(stu, "departure"),
            }
            for stu in update.stop_time_update
            if stu.schedule_relationship != _STU_SKIPPED
        ]
        if stops:
            trips.append({"trip_id": update.trip.trip_id, "stops": stops})
    return {"trips": trips}


def _translation_text(block) -> str:
    fallback = ""
    for entry in block.translation:
        text = entry.text.strip()
        if entry.language == "en" and text:
            return text
        if not fallback and text:
            fallback = text
    return fallback


def parse_alerts_feed(raw: bytes) -> dict:
    """Protobuf bytes → {'alerts': [{'id', 'header', 'description',
    'periods': [{'start': epoch|None, 'end': epoch|None}]}]}.

    Activeness is time-dependent and so is NOT decided here (the parse is
    cached for ALERTS_TTL_S) — bart_pairs.parse_alerts filters per request.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(raw)
    except DecodeError as exc:
        raise ValueError(f"undecodable GTFS-RT feed: {exc}") from exc

    alerts = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        alerts.append(
            {
                "id": entity.id,
                "header": _translation_text(alert.header_text),
                "description": _translation_text(alert.description_text),
                "periods": [
                    {
                        "start": period.start if period.HasField("start") else None,
                        "end": period.end if period.HasField("end") else None,
                    }
                    for period in alert.active_period
                ],
            }
        )
    return {"alerts": alerts}


_PARSERS = {
    "tripupdate.aspx": parse_trip_updates,
    "alerts.aspx": parse_alerts_feed,
}


async def _fetch(endpoint: str) -> dict:
    resp = await _upstream.client().get(f"{BASE_URL}/{endpoint}")
    resp.raise_for_status()
    return _PARSERS[endpoint](resp.content)


async def get_trip_updates() -> tuple[dict, datetime, bool]:
    payload, fetched_at, stale = await _upstream.get_cached(
        "tripupdate.aspx", TRIP_UPDATES_TTL_S, _fetch
    )
    return payload, fetched_at, stale


async def get_alerts() -> tuple[dict, datetime, bool]:
    payload, fetched_at, stale = await _upstream.get_cached("alerts.aspx", ALERTS_TTL_S, _fetch)
    return payload, fetched_at, stale


def upstream_calls_last_hour() -> int:
    return _upstream.calls_last_hour()


def cache_status() -> dict:
    """Cache ages for /api/health. Never triggers upstream calls."""
    return _upstream.cache_status(
        {"bart_trip_updates": "tripupdate.aspx", "bart_alerts": "alerts.aspx"}
    )


def reset() -> None:
    """Clear all module state (tests only)."""
    _upstream.reset()
