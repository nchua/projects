"""BART pair logic: direct joins, transfer itineraries, and alert filtering.

Pure functions over the plain-dict feed produced by app.bart — no protobuf,
no IO, fully unit-testable (SPEC-BART §5). All comparisons happen on epoch
seconds; ISO strings are produced only at the output boundary.

Direction is never inferred: a trip serves a pair iff its arrival at the
destination is strictly later than its departure at the origin (§5.1) —
wrong-direction trains fall out naturally, and the SFO/MLBR wye (where
compass direction lies) is handled for free.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app import bart_stations
from app.departures import (  # same thresholds as Caltrain (§8)
    DEPARTURE_GRACE_S,
    LATE_THRESHOLD_SECONDS,
)

TRANSFER_DEFAULT_MIN_S = 180
TRANSFER_LEG1_CANDIDATES = 10
# Connection-at-risk thresholds (SPEC-V2 §2): slack below 120 s flags any
# connection; an *estimated* (schedule-projected) leg-1 arrival carries error
# a realtime one doesn't, so it widens the band to 300 s instead of always
# flagging — estimation with plenty of slack is not at risk.
TRANSFER_AT_RISK_SLACK_S = 120
TRANSFER_AT_RISK_ESTIMATED_SLACK_S = 300

_OAK_SHUTTLE_ABBRS = ("OAKL", "COLS")

# Internal-only keys carried on rows/itineraries for stitching and ranking;
# stripped at the output boundary.
_META_KEYS = ("_dep_epoch", "_arr_epoch", "_dep_platform", "_arr_platform")


def _iso(epoch: int | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def index_feed(feed: dict) -> dict[str, dict[str, dict]]:
    """{trip_id: {parent_abbr: stu}} with unknown stop_ids skipped (§5.1-1).

    Keeps the first STU per parent (the arrival side of the SFIA wye dwell,
    should the feed ever carry both rows).
    """
    index: dict[str, dict[str, dict]] = {}
    for trip in feed.get("trips", []):
        stops: dict[str, dict] = {}
        for stu in trip["stops"]:
            parent = bart_stations.parent_of_platform(stu["stop_id"])
            if parent is not None:
                stops.setdefault(parent, stu)
        if stops:
            index.setdefault(trip["trip_id"], stops)
    return index


def _event_time(event: dict | None) -> int | None:
    return event["time"] if event else None


def _event_delay(event: dict | None) -> int | None:
    return event["delay"] if event else None


def _resolve_arrival(
    stops: dict[str, dict],
    trip_id: str,
    origin_abbr: str,
    destination_abbr: str,
    dep_epoch: int,
) -> tuple[dict | None, int | None, str | None] | None:
    """(arrival_payload, arrival_epoch, arrival_platform) or None to drop the
    row. Resolution priority per §5.2; the strictly-later-than-departure check
    doubles as the direction filter.
    """
    stu = stops.get(destination_abbr)
    if stu is not None:
        arr_epoch = _event_time(stu["arrival"]) or _event_time(stu["departure"])
        if arr_epoch is None:
            return {"payload": None, "epoch": None, "platform": None}
        if arr_epoch <= dep_epoch:
            return None  # wrong direction (or already passed) — drop
        delay = _event_delay(stu["arrival"])
        payload = {
            "aimed": _iso(arr_epoch - delay if delay is not None else arr_epoch),
            "expected": _iso(arr_epoch),
        }
        return {"payload": payload, "epoch": arr_epoch, "platform": stu["stop_id"]}

    pattern = bart_stations.trip_pattern(trip_id)
    if pattern is None:
        return None  # unknown trip and no RT arrival — direct_rows handles the fallback

    if destination_abbr not in pattern or origin_abbr not in pattern:
        return None  # short-turn / never serves the pair (§5.2-3)
    dest_pos, dest_offset = pattern[destination_abbr]
    origin_pos, _ = pattern[origin_abbr]
    if dest_pos <= origin_pos:
        return None  # destination behind the origin on this pattern — drop

    # Truncated-terminal projection (§5.2-2): anchor on the last RT stop that
    # exists in the pattern and add the static delta. Epoch-based — no dates.
    anchor_epoch = anchor_offset = anchor_delay = None
    for parent, stu in stops.items():
        position = pattern.get(parent)
        epoch = _event_time(stu["arrival"]) or _event_time(stu["departure"])
        if position is None or epoch is None:
            continue
        if anchor_offset is None or position[1] > anchor_offset:
            anchor_offset = position[1]
            anchor_epoch = epoch
            anchor_delay = _event_delay(stu["arrival"])
            if anchor_delay is None:  # 0 is a real value — only fall through on None
                anchor_delay = _event_delay(stu["departure"])
    if anchor_epoch is None or anchor_offset is None or dest_offset <= anchor_offset:
        return {"payload": None, "epoch": None, "platform": None}

    projected = anchor_epoch + (dest_offset - anchor_offset)
    if projected <= dep_epoch:  # sanity: never arrive before departing
        return {"payload": None, "epoch": None, "platform": None}
    payload = {
        "aimed": _iso(projected - anchor_delay if anchor_delay is not None else projected),
        "expected": _iso(projected),
        "estimated": True,
    }
    return {"payload": payload, "epoch": projected, "platform": None}


def _headsign(trip_id: str, stops: dict[str, dict]) -> str:
    """'to Antioch' — pattern terminus, or the last RT stop for unknown trips
    (eBART shuttles). Never GTFS trip_headsign (§4.4)."""
    terminus = bart_stations.trip_terminus(trip_id)
    if terminus is None:
        last_abbr = max(
            (stu for stu in stops.values() if _event_time(stu["arrival"]) is not None),
            key=lambda stu: stu["arrival"]["time"],
            default=None,
        )
        if last_abbr is not None:
            station = bart_stations.by_abbr(
                bart_stations.parent_of_platform(last_abbr["stop_id"]) or ""
            )
            terminus = station.name if station else None
    return f"to {terminus}" if terminus else ""


def direct_rows(
    index: dict[str, dict[str, dict]],
    origin_abbr: str,
    destination_abbr: str,
    limit: int,
    now_epoch: int,
) -> list[dict]:
    """Direct-trip rows for the pair, sorted by effective departure (§5.1).

    Rows carry _META_KEYS for transfer stitching; strip_meta() before output.
    """
    rows: list[dict] = []
    for trip_id, stops in index.items():
        stu = stops.get(origin_abbr)
        if stu is None:
            continue
        dep_epoch = _event_time(stu["departure"]) or _event_time(stu["arrival"])
        if dep_epoch is None or now_epoch - dep_epoch > DEPARTURE_GRACE_S:
            continue

        line, line_color = bart_stations.trip_line(trip_id)
        headsign = _headsign(trip_id, stops)

        resolved = _resolve_arrival(stops, trip_id, origin_abbr, destination_abbr, dep_epoch)
        if resolved is None:
            if bart_stations.trip_pattern(trip_id) is not None:
                continue  # known trip that doesn't serve the pair (§5.2-3)
            # Unknown trip with no RT arrival (§5.2-4, amended during
            # implementation): project via the static delta between the two
            # stations, using only patterns consistent with the trip's
            # observed stop order. This is what lets eBART-shuttle legs
            # (whose STUs never include PITT) resolve, and what keeps every
            # pair alive after a GTFS rotation — honest, marked estimated.
            observed = [
                (parent, epoch)
                for parent, s in stops.items()
                if (epoch := _event_time(s["arrival"]) or _event_time(s["departure"])) is not None
            ]
            ride = bart_stations.static_ride(origin_abbr, destination_abbr, observed)
            if ride is None:
                continue
            projected = dep_epoch + ride["delta_s"]
            resolved = {
                "payload": {"aimed": _iso(projected), "expected": _iso(projected), "estimated": True},
                "epoch": projected,
                "platform": None,
            }
            line = ride["line"]
            line_color = bart_stations.LINE_COLORS.get(line, bart_stations.NEUTRAL_LINE_COLOR)
            if ride["terminus"]:
                headsign = f"to {ride['terminus']}"

        delay = _event_delay(stu["departure"])
        if delay is None:
            delay = _event_delay(stu["arrival"])
        if delay is not None and delay >= LATE_THRESHOLD_SECONDS:
            status = "late"
        else:
            status = "on_time"

        rows.append(
            {
                "trip": trip_id,
                "line": line,
                "line_color": line_color,
                "headsign": headsign,
                "departure": {
                    "aimed": _iso(dep_epoch - delay if delay is not None else dep_epoch),
                    "expected": _iso(dep_epoch),
                },
                "arrival": resolved["payload"],
                "delay_seconds": delay,
                "status": status,
                "_dep_epoch": dep_epoch,
                "_arr_epoch": resolved["epoch"],
                "_dep_platform": stu["stop_id"],
                "_arr_platform": resolved["platform"],
            }
        )

    rows.sort(key=lambda row: row["_dep_epoch"])
    return rows[:limit]


def strip_meta(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in _META_KEYS}


def _shuttle_rows(from_abbr: str, to_abbr: str, ready_epoch: int, count: int) -> list[dict]:
    """Synthesized OAK-shuttle legs (§5.5-5, amended during implementation:
    the people-mover never appears in GTFS-RT — verified live 2026-07-02).

    A rung ladder at headway spacing, first rung a full headway after ready:
    shuttles depart at least every headway_s, so a rider is guaranteed aboard
    by each rung — conservative in both directions of the trip. Marked
    estimated and status 'scheduled' (the feed carries no times for it).
    """
    shuttle = bart_stations.OAK_SHUTTLE
    ride_s = (shuttle or {}).get("rides", {}).get(f"{from_abbr}:{to_abbr}")
    if ride_s is None:
        return []
    destination = bart_stations.by_abbr(to_abbr)
    line, line_color = "Grey", bart_stations.LINE_COLORS["Grey"]
    rows = []
    for rung in range(1, count + 1):
        dep_epoch = ready_epoch + rung * shuttle["headway_s"]
        arr_epoch = dep_epoch + ride_s
        rows.append(
            {
                "trip": None,
                "line": line,
                "line_color": line_color,
                "headsign": f"to {destination.name}" if destination else "",
                "departure": {"aimed": _iso(dep_epoch), "expected": _iso(dep_epoch), "estimated": True},
                "arrival": {"aimed": _iso(arr_epoch), "expected": _iso(arr_epoch), "estimated": True},
                "delay_seconds": None,
                "status": "scheduled",
                "_dep_epoch": dep_epoch,
                "_arr_epoch": arr_epoch,
                "_dep_platform": None,
                "_arr_platform": None,
            }
        )
    return rows


# --- transfer itineraries (§5.5) --------------------------------------------


def _as_itinerary(row: dict, origin_id: str, destination_id: str) -> dict:
    """A direct row as a 1-leg itinerary (uniform shape for stitching)."""
    leg = dict(row)
    leg["from"] = origin_id
    leg["to"] = destination_id
    return {
        "legs": [leg],
        "transfers": [],
        "_dep_epoch": row["_dep_epoch"],
        "_arr_epoch": row["_arr_epoch"],
        "_dep_platform": row["_dep_platform"],
        "_arr_platform": row["_arr_platform"],
    }


def _stitch(
    firsts: list[dict],
    seconds: list[dict],
    at_station: bart_stations.Station,
    default_min_s: int = TRANSFER_DEFAULT_MIN_S,
) -> list[dict]:
    """Join two itinerary lists at a station: for each first, the earliest
    second whose departure clears the min-transfer window computed on
    *expected* times — so a late first leg rolls to the next feasible
    connection with no extra code (§5.5-3). default_min_s covers platform
    pairs absent from the bundled table (the CT↔BA stitch passes its own —
    SPEC-V2 §7.3).

    A connection that clears the minimum with little to spare is kept but
    flagged at_risk on the transfer entry (SPEC-V2 §2) — the flag warns, it
    never filters."""
    stitched = []
    for first in firsts:
        if first["_arr_epoch"] is None:
            continue
        best = best_min_s = None
        for second in seconds:
            min_s = bart_stations.transfer_min_s(
                first["_arr_platform"], second["_dep_platform"], default_min_s
            )
            if second["_dep_epoch"] >= first["_arr_epoch"] + min_s:
                if best is None or second["_dep_epoch"] < best["_dep_epoch"]:
                    best, best_min_s = second, min_s
        if best is None or best["_arr_epoch"] is None:
            continue
        wait_minutes = round((best["_dep_epoch"] - first["_arr_epoch"]) / 60)
        transfer = {
            "station": at_station.id,
            "station_name": at_station.name,
            "wait_minutes": wait_minutes,
        }
        slack_s = best["_dep_epoch"] - (first["_arr_epoch"] + best_min_s)
        leg1_arrival = first["legs"][-1].get("arrival") if first["legs"] else None
        leg1_estimated = bool(leg1_arrival and leg1_arrival.get("estimated"))
        if slack_s < TRANSFER_AT_RISK_SLACK_S or (
            leg1_estimated and slack_s < TRANSFER_AT_RISK_ESTIMATED_SLACK_S
        ):
            transfer["at_risk"] = True
        stitched.append(
            {
                "legs": first["legs"] + best["legs"],
                "transfers": first["transfers"] + [transfer] + best["transfers"],
                "_dep_epoch": first["_dep_epoch"],
                "_arr_epoch": best["_arr_epoch"],
                "_dep_platform": first["_dep_platform"],
                "_arr_platform": best["_arr_platform"],
            }
        )
    return stitched


def _prune_dominated(itineraries: list[dict]) -> list[dict]:
    """Keep the Pareto frontier: drop an itinerary when another departs no
    earlier AND arrives no later (§5.5-4)."""
    ordered = sorted(itineraries, key=lambda i: (i["_arr_epoch"], -i["_dep_epoch"]))
    kept: list[dict] = []
    best_departure = None
    for itinerary in ordered:
        if best_departure is not None and itinerary["_dep_epoch"] <= best_departure:
            continue
        kept.append(itinerary)
        best_departure = itinerary["_dep_epoch"]
    return kept


def _one_transfer_itineraries(
    index: dict[str, dict[str, dict]],
    origin: bart_stations.Station,
    destination: bart_stations.Station,
    now_epoch: int,
) -> list[dict]:
    """All single-transfer candidates via T ∈ reaches(origin) with
    destination ∈ reaches(T) (§5.5-1). Static reachability only generates
    candidates — every leg is realtime-joined, so phantoms cost nothing."""
    itineraries: list[dict] = []
    for abbr in sorted(bart_stations.reaches(origin.abbr)):
        if destination.abbr not in bart_stations.reaches(abbr):
            continue
        via = bart_stations.by_abbr(abbr)
        if via is None:
            continue
        leg1 = [
            _as_itinerary(row, origin.id, via.id)
            for row in direct_rows(index, origin.abbr, abbr, TRANSFER_LEG1_CANDIDATES, now_epoch)
        ]
        if not leg1:
            continue
        leg2 = [
            _as_itinerary(row, via.id, destination.id)
            for row in direct_rows(
                index, abbr, destination.abbr, TRANSFER_LEG1_CANDIDATES, now_epoch
            )
        ]
        itineraries.extend(_stitch(leg1, leg2, via))
    return itineraries


def transfer_itineraries(
    index: dict[str, dict[str, dict]],
    origin: bart_stations.Station,
    destination: bart_stations.Station,
    limit: int,
    now_epoch: int,
) -> list[dict]:
    """Transfer itineraries for a zero-direct pair, ranked by arrival and
    Pareto-pruned. The OAK shuttle stitch (§5.5-5) is the only way an
    itinerary reaches 3 legs."""
    itineraries = _one_transfer_itineraries(index, origin, destination, now_epoch)

    cols = bart_stations.by_abbr("COLS")
    if not itineraries and cols is not None and origin.abbr == "OAKL":
        # leg 1 is the shuttle: a now-anchored ladder is exactly right —
        # the rider is standing at the airport now
        shuttle = [
            _as_itinerary(row, origin.id, cols.id)
            for row in direct_rows(index, "OAKL", "COLS", TRANSFER_LEG1_CANDIDATES, now_epoch)
            or _shuttle_rows("OAKL", "COLS", now_epoch, TRANSFER_LEG1_CANDIDATES)
        ]
        rest = [
            _as_itinerary(row, cols.id, destination.id)
            for row in direct_rows(
                index, "COLS", destination.abbr, TRANSFER_LEG1_CANDIDATES, now_epoch
            )
        ] or _one_transfer_itineraries(index, cols, destination, now_epoch)
        itineraries = _stitch(shuttle, rest, cols)
    elif not itineraries and cols is not None and destination.abbr == "OAKL":
        rest = [
            _as_itinerary(row, origin.id, cols.id)
            for row in direct_rows(index, origin.abbr, "COLS", TRANSFER_LEG1_CANDIDATES, now_epoch)
        ] or _one_transfer_itineraries(index, origin, cols, now_epoch)
        rt_shuttle = direct_rows(index, "COLS", "OAKL", TRANSFER_LEG1_CANDIDATES, now_epoch)
        if rt_shuttle:
            itineraries = _stitch(
                rest, [_as_itinerary(row, cols.id, destination.id) for row in rt_shuttle], cols
            )
        else:
            # Synthesized last leg is anchored at each connection's arrival —
            # a now-anchored ladder would run out of rungs for distant origins
            # whose first legs arrive at Coliseum hours from now.
            itineraries = []
            for first in rest:
                if first["_arr_epoch"] is None:
                    continue
                rungs = [
                    _as_itinerary(row, cols.id, destination.id)
                    for row in _shuttle_rows("COLS", "OAKL", first["_arr_epoch"], 2)
                ]
                itineraries.extend(_stitch([first], rungs, cols))

    return _prune_dominated(itineraries)[:limit]


def _itinerary_payload(itinerary: dict) -> dict:
    """Public shape (§7.2): top-level departure/arrival/delay/status mirror
    leg 1's origin and the last leg's arrival, so the row renderer shares one
    code path with direct rows."""
    legs = [strip_meta(leg) for leg in itinerary["legs"]]
    first, last = legs[0], legs[-1]
    return {
        "trip": first["trip"],
        "line": first["line"],
        "line_color": first["line_color"],
        "headsign": first["headsign"],
        "departure": first["departure"],
        "arrival": last["arrival"],
        "delay_seconds": first["delay_seconds"],
        "status": first["status"],
        "legs": legs,
        "transfers": itinerary["transfers"],
    }


def pair_departures(
    feed: dict,
    origin: bart_stations.Station,
    destination: bart_stations.Station,
    limit: int,
    now: datetime | None = None,
) -> list[dict]:
    """Direct rows for the pair; transfer itineraries only when no direct
    trip exists (§5.5-7 — the two are never mixed in one response)."""
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    index = index_feed(feed)

    rows = direct_rows(index, origin.abbr, destination.abbr, limit, now_epoch)
    if not rows and {origin.abbr, destination.abbr} == set(_OAK_SHUTTLE_ABBRS):
        rows = _shuttle_rows(origin.abbr, destination.abbr, now_epoch, limit)
    if rows:
        return [strip_meta(row) for row in rows]

    itineraries = transfer_itineraries(index, origin, destination, limit, now_epoch)
    return [_itinerary_payload(itinerary) for itinerary in itineraries]


# --- alerts (§7.4) -----------------------------------------------------------

_GENERIC_HEADER = "bart.gov alert"
_BANNER_MAX_CHARS = 120
_SENTENCE_ENDS = (". ", "! ", "? ")


def _split_banner(description: str) -> tuple[str, str]:
    """(header, remainder): the first ~120 chars of the description,
    sentence-boundary truncated, plus whatever follows — the feed's own
    header_text is a useless generic 'BART.gov Alert'. Splitting (rather than
    copying) keeps the banner from reading the same text twice."""
    if len(description) <= _BANNER_MAX_CHARS:
        return description, ""
    window = description[: _BANNER_MAX_CHARS + 1]
    cut = max(window.rfind(end) + len(end.rstrip()) for end in _SENTENCE_ENDS)
    if cut > 0:
        return window[:cut].strip(), description[cut:].strip()
    space = window.rfind(" ")
    cut = space if space > 0 else _BANNER_MAX_CHARS
    return window[:cut].strip() + "…", description[cut:].strip()


def parse_alerts(parsed: dict, now: datetime | None = None) -> list[dict]:
    """Currently-active alerts as {id, header, description, active_period}.
    No periods at all → always active (same rule as the Caltrain parser)."""
    now_epoch = int((now or datetime.now(timezone.utc)).timestamp())
    alerts = []
    for alert in parsed.get("alerts", []):
        periods = alert["periods"]
        active_start = active_end = None
        is_active = not periods
        for period in periods:
            start, end = period["start"], period["end"]
            if (start is None or start <= now_epoch) and (end is None or now_epoch <= end):
                is_active, active_start, active_end = True, start, end
                break
        if not is_active:
            continue

        description = alert["description"].strip()
        header = alert["header"].strip()
        if not header or header.lower() == _GENERIC_HEADER:
            header, description = _split_banner(description)
        if not header and not description:
            continue

        alerts.append(
            {
                "id": alert["id"],
                "header": header,
                "description": description,
                "active_period": {"start": _iso(active_start), "end": _iso(active_end)},
            }
        )
    return alerts
