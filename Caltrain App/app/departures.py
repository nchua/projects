"""Parsing for 511 payloads: StopMonitoring pair-join and service alerts.

Pure functions over already-decoded payload dicts — unit-testable with no IO.
All time handling is full aware-datetime comparison; never clock times
(midnight-crossing trips are safe under RFC3339 timestamps).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app import schedule

LATE_THRESHOLD_SECONDS = 120
DEPARTURE_GRACE_S = 30


def ensure_list(value: Any) -> list:
    """511 collapses single-element arrays to bare objects; normalize."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_time(value: str | None) -> datetime | None:
    """RFC3339 → aware datetime (Python ≥3.11 parses trailing 'Z' natively)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def train_type(line_ref: str | None) -> str:
    """Normalize LineRef case-insensitively by substring — handles both
    long forms ('Local Weekday', 'Limited') and codes (LOC/LIM/EXP/SCC)."""
    if not line_ref:
        return "Train"
    low = line_ref.lower()
    if "exp" in low:
        return "Express"
    if "lim" in low:
        return "Limited"
    if "scc" in low or "south" in low:
        return "South County"
    if "loc" in low:
        return "Local"
    return line_ref


def _service_delivery(payload: dict) -> dict:
    """Top level is ServiceDelivery with no Siri wrapper — accept both."""
    return payload.get("ServiceDelivery") or payload.get("Siri", {}).get("ServiceDelivery") or {}


def index_visits(payload: dict) -> dict[str, dict[str, dict]]:
    """Build {train_number: {stop_code: visit}} from an all-stops payload.

    Train number (DatedVehicleJourneyRef) is the join key between a train's
    visit at the origin platform and its visit at the destination platform.
    """
    index: dict[str, dict[str, dict]] = {}
    for delivery in ensure_list(_service_delivery(payload).get("StopMonitoringDelivery")):
        for visit in ensure_list(delivery.get("MonitoredStopVisit")):
            journey = visit.get("MonitoredVehicleJourney") or {}
            train = (journey.get("FramedVehicleJourneyRef") or {}).get("DatedVehicleJourneyRef")
            call = journey.get("MonitoredCall") or {}
            stop = call.get("StopPointRef") or visit.get("MonitoringRef")
            if not train or not stop:
                continue
            index.setdefault(str(train), {})[str(stop)] = visit
    return index


_SKIP = object()  # sentinel: this train does not serve the destination


def _resolve_arrival(
    stops: dict[str, dict],
    journey: dict,
    train: str,
    destination_stop: str,
    aimed: datetime | None,
    effective: datetime,
    delay: int | None,
) -> dict | None | object:
    """Arrival for one train at destination_stop, or _SKIP to drop the row.

    Priority order:
    1. The train's realtime visit at the destination platform (times
       missing/unparseable → arrival None, row kept).
    2. The bundled GTFS schedule + the train's current delay, marked
       estimated — needed because StopMonitoring omits arrival-only
       (terminal) stops and truncates visits ~90 min out (verified
       2026-07-01); the trip's GTFS stop list also decides the
       express-skips-station exclusion.
    3. Trip unknown to the bundled GTFS: keep with arrival None only if
       DestinationRef matches, else _SKIP.
    """
    visit = stops.get(destination_stop)
    if visit is not None:
        call = (visit.get("MonitoredVehicleJourney") or {}).get("MonitoredCall") or {}
        arrival_aimed = parse_time(call.get("AimedArrivalTime"))
        arrival_expected = parse_time(call.get("ExpectedArrivalTime"))
        if arrival_aimed or arrival_expected:
            return {"aimed": _iso(arrival_aimed), "expected": _iso(arrival_expected)}
        return None

    known_stops = schedule.trip_stops(train)
    if known_stops is not None:
        if destination_stop not in known_stops:
            return _SKIP
        service_date = (journey.get("FramedVehicleJourneyRef") or {}).get("DataFrameRef")
        sched = schedule.scheduled_arrival(train, destination_stop, service_date, fallback_date=effective)
        # sanity: a schedule-derived arrival must not precede departure
        if sched is None or (aimed and sched < aimed):
            return None
        return {
            "aimed": _iso(sched),
            "expected": _iso(sched + timedelta(seconds=delay)) if delay is not None else None,
            "estimated": True,
        }

    return None if journey.get("DestinationRef") == destination_stop else _SKIP


def pair_departures(
    payload: dict,
    origin_stop: str,
    destination_stop: str,
    limit: int,
    now: datetime | None = None,
) -> list[dict]:
    """Upcoming departures at origin_stop joined to the same train's arrival
    at destination_stop (resolution order: see _resolve_arrival).

    No ExpectedDepartureTime → scheduled-only row, never dropped.
    """
    now = now or datetime.now(timezone.utc)
    rows: list[tuple[datetime, dict]] = []

    for train, stops in index_visits(payload).items():
        origin_visit = stops.get(origin_stop)
        if origin_visit is None:
            continue

        journey = origin_visit.get("MonitoredVehicleJourney") or {}
        call = journey.get("MonitoredCall") or {}
        aimed = parse_time(call.get("AimedDepartureTime"))
        expected = parse_time(call.get("ExpectedDepartureTime"))
        effective = expected or aimed
        if effective is None or (now - effective).total_seconds() > DEPARTURE_GRACE_S:
            continue

        delay = int((expected - aimed).total_seconds()) if expected and aimed else None

        arrival = _resolve_arrival(stops, journey, train, destination_stop, aimed, effective, delay)
        if arrival is _SKIP:
            continue
        if expected is None:
            status = "scheduled"
        elif delay is not None and delay >= LATE_THRESHOLD_SECONDS:
            status = "late"
        else:
            status = "on_time"

        line_ref = journey.get("LineRef")
        rows.append(
            (
                effective,
                {
                    "train": train,
                    "train_type": train_type(line_ref),
                    "line_ref_raw": line_ref,
                    "departure": {"aimed": _iso(aimed), "expected": _iso(expected)},
                    "arrival": arrival,
                    "delay_seconds": delay,
                    "status": status,
                },
            )
        )

    rows.sort(key=lambda pair: pair[0])
    return [row for _, row in rows[:limit]]


# --- service alerts (GTFS-RT JSON) -----------------------------------------
# 511 serves PascalCase keys with lowercase exceptions (verified 2026-07-01:
# Entities / Alert / ActivePeriods{Start,End} / HeaderText.Translations
# {Text,Language}, but lowercase `cause`/`effect`). Read defensively in both
# PascalCase and GTFS-spec snake_case.


def _first(mapping: dict, *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _translation_text(block: dict | None) -> str:
    if not block:
        return ""
    fallback = ""
    for entry in ensure_list(_first(block, "Translations", "translation")):
        text = (_first(entry, "Text", "text") or "").strip()
        language = _first(entry, "Language", "language")
        if language == "en" and text:
            return text
        if not fallback and text:
            fallback = text
    return fallback


def _epoch(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def parse_alerts(payload: dict, now: datetime | None = None) -> list[dict]:
    """Flatten currently-active alerts to {id, header, description, active_period}."""
    now = now or datetime.now(timezone.utc)
    alerts = []
    for entity in ensure_list(_first(payload, "Entities", "entity")):
        alert = _first(entity, "Alert", "alert")
        if not alert:
            continue

        periods = ensure_list(_first(alert, "ActivePeriods", "active_period"))
        active_start = active_end = None
        is_active = not periods  # no periods at all → treat as always active
        for period in periods:
            start = _epoch(_first(period, "Start", "start"))
            end = _epoch(_first(period, "End", "end"))
            if (start is None or start <= now) and (end is None or now <= end):
                is_active, active_start, active_end = True, start, end
                break
        if not is_active:
            continue

        header = _translation_text(_first(alert, "HeaderText", "header_text"))
        description = _translation_text(_first(alert, "DescriptionText", "description_text"))
        if not header and not description:
            continue

        alerts.append(
            {
                "id": str(_first(entity, "Id", "id") or ""),
                "header": header,
                "description": description,
                "active_period": {"start": _iso(active_start), "end": _iso(active_end)},
            }
        )
    return alerts
