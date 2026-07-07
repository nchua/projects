"""BART GTFS-Realtime upstream client (SPEC-BART §6.2).

No API key and no published rate limit — the guard here is a runaway-bug
backstop, not a budget (worst continuous case is ~132 calls/hr at the chosen
TTLs). Protobuf is parsed immediately at fetch time into plain dicts and the
*parsed* form is cached, so pure pair logic never sees protobuf objects and
a DecodeError counts as a fetch failure (→ serve stale).

Both endpoints 301/307-redirect; the shared client follows redirects.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from app import bart_stations
from app.upstream import Upstream

BASE_URL = "https://api.bart.gov/gtfsrt"
# Legacy JSON API — the ONLY bart.gov surface that needs the personal key
# (SPEC-V2 §6.2). The demo key is forbidden in production; no key → the
# elevator feature is silently absent.
ELEV_URL = "https://api.bart.gov/api/bsa.aspx"

TRIP_UPDATES_TTL_S = 30
ALERTS_TTL_S = 300
ELEV_TTL_S = 300
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
    """Protobuf bytes → {'trips': [...], 'canceled_trips': [...]}, each entry
    {'trip_id', 'stops': [...]}.

    CANCELED trips move to their own list (SPEC-V2 §5.2) so every existing
    consumer of 'trips' — the pair join, transfer stitching — is untouched and
    canceled trips can never leak into itineraries. Their stops are kept if
    the feed supplies them (never observed live; the synthetic fixture pins
    both shapes). SKIPPED stops are dropped as before.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(raw)
    except DecodeError as exc:  # count as fetch failure → serve stale
        raise ValueError(f"undecodable GTFS-RT feed: {exc}") from exc

    trips = []
    canceled = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        stops = [
            {
                "stop_id": stu.stop_id,
                "arrival": _event(stu, "arrival"),
                "departure": _event(stu, "departure"),
            }
            for stu in update.stop_time_update
            if stu.schedule_relationship != _STU_SKIPPED
        ]
        if update.trip.schedule_relationship == _CANCELED:
            canceled.append({"trip_id": update.trip.trip_id, "stops": stops})
        elif stops:
            trips.append({"trip_id": update.trip.trip_id, "stops": stops})
    return {"trips": trips, "canceled_trips": canceled}


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
        # informed_entity stop_ids were empty in every capture (agency-only —
        # SPEC-V2 §3.1) but are plumbed through for a uniform alert shape;
        # they start working the day BART populates them
        stops: list[str] = []
        for informed in alert.informed_entity:
            if informed.stop_id and informed.stop_id not in stops:
                stops.append(informed.stop_id)
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
                "stops": stops,
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


# --- elevator advisories (SPEC-V2 §6.2) ---------------------------------------

# XML-converted JSON: singletons collapse to bare objects (same class of quirk
# as 511) and text hides under #cdata-section.


def _ensure_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _cdata(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("#cdata-section") or "").strip()
    return str(value or "").strip()


# station scoping is parsed from the prose ("MLBR: Station - …; RICH: Station")
# — tokens before a colon, validated against the station registry
_ELEV_ABBR_RE = re.compile(r"\b([A-Z0-9]{2,4}):")


def parse_elevator_advisories(payload: dict) -> list[dict]:
    """bsa.aspx?cmd=elev JSON → alert-shaped advisories.

    The feed posts ONE generic entry whose description covers every outage
    (verified live 2026-07-06, fixture elev.json). Ids are synthetic and
    set-stable ('elev:' + sorted abbrs) — the feed's own @id is time-derived
    and would break session-dismiss. A zero-outage message ("all elevators
    are in service") produces no advisories; prose with no resolvable
    station degrades to an unscoped banner alert, never dropped.
    """
    root = payload.get("root") if isinstance(payload, dict) else None
    advisories = []
    for entry in _ensure_list(root.get("bsa") if isinstance(root, dict) else None):
        if not isinstance(entry, dict):
            continue  # unexpected XML→JSON shape — skip, never crash (§6.2)
        description = _cdata(entry.get("description"))
        lowered = description.lower()
        if not description or "out of service" not in lowered:
            continue  # zero-outage message ("all elevators are in service") or noise
        abbrs: list[str] = []
        for token in _ELEV_ABBR_RE.findall(description):
            if bart_stations.by_abbr(token) and token not in abbrs:
                abbrs.append(token)
        if not abbrs and re.search(r"\bno (?:elevators?|escalators?)\b", lowered):
            continue  # negated zero-outage phrasing — fail closed (§6.2 ⚠ VERIFY)
        if abbrs:
            names = ", ".join(bart_stations.by_abbr(a).name for a in abbrs)
            header = f"Elevator out of service at {names}"
            alert_id = "elev:" + ",".join(sorted(abbrs))
        else:
            header, description = description, ""
            alert_id = "elev:unscoped"
        advisories.append(
            {
                "id": alert_id,
                "type": "elevator",
                "header": header,
                "description": description,
                "active_period": {"start": None, "end": None},
                "stops": abbrs,
            }
        )
    return advisories


async def _fetch_elev(endpoint: str) -> list[dict]:
    key = os.environ.get("BART_API_KEY", "")
    resp = await _upstream.client().get(f"{ELEV_URL}?cmd=elev&key={key}&json=y")
    resp.raise_for_status()
    return parse_elevator_advisories(resp.json())


async def get_elevator_advisories() -> tuple[list[dict], datetime | None, bool]:
    """Parsed advisories, or ([], None, False) when no personal key is
    configured — the feature is key-gated and silently absent (§6.2)."""
    if not os.environ.get("BART_API_KEY"):
        return [], None, False
    advisories, fetched_at, stale = await _upstream.get_cached("bsa_elev", ELEV_TTL_S, _fetch_elev)
    return advisories, fetched_at, stale


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
        {"bart_trip_updates": "tripupdate.aspx", "bart_alerts": "alerts.aspx", "bart_elev": "bsa_elev"}
    )


def reset() -> None:
    """Clear all module state (tests only)."""
    _upstream.reset()
