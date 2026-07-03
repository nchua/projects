"""BART station + trip-pattern registry, loaded once from data/bart_*.json.

Like app.schedule this is NOT a schedule engine: patterns are only ever read
as offsets between two stops of the same realtime-supplied trip, so no
calendar / service-date logic exists anywhere (SPEC-BART §4.2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Route → line map (SPEC-BART §4.4). GTFS route_short_name is "Yellow-S" etc.;
# both directions collapse to the line. Colors are the dark-theme mockup tokens.
LINE_COLORS: dict[str, str] = {
    "Yellow": "#ffe14d",
    "Orange": "#ffa64d",
    "Green": "#55c975",
    "Red": "#ff7070",
    "Blue": "#4db8e8",
    "Grey": "#b0bec7",
}
NEUTRAL_LINE_COLOR = "#c8cdd2"

ROUTE_LINES: dict[str, str] = {
    "1": "Yellow", "2": "Yellow",
    "3": "Orange", "4": "Orange",
    "5": "Green", "6": "Green",
    "7": "Red", "8": "Red",
    "11": "Blue", "12": "Blue",
    "19": "Grey", "20": "Grey",
}


@dataclass(frozen=True)
class Station:
    id: str
    abbr: str
    name: str
    lat: float
    lon: float
    lines: list[str]


_stations_raw: dict = json.loads((_DATA_DIR / "bart_stations.json").read_text(encoding="utf-8"))
_trips_raw: dict = json.loads((_DATA_DIR / "bart_trips.json").read_text(encoding="utf-8"))

STATIONS: list[Station] = [Station(**s) for s in _stations_raw["stations"]]
_BY_ID: dict[str, Station] = {s.id: s for s in STATIONS}
_BY_ABBR: dict[str, Station] = {s.abbr: s for s in STATIONS}
PLATFORMS: dict[str, str] = _stations_raw["platforms"]
RAW_STATIONS: list[dict] = _stations_raw["stations"]

# patterns[i] = ordered [parent_abbr, seconds_offset_from_first_arrival] pairs
PATTERNS: list[list[list]] = _trips_raw["patterns"]
# trips[trip_id] = [pattern_index, first_arrival_seconds_after_midnight, route_id]
TRIPS: dict[str, list] = _trips_raw["trips"]
# directed platform-level minimum transfer seconds; absent pairs use the default
TRANSFERS: dict[str, dict[str, int]] = _trips_raw["transfers"]
# {'headway_s': int, 'rides': {'OAKL:COLS': s, 'COLS:OAKL': s}} — the airport
# people-mover never appears in GTFS-RT, so its leg is synthesized from these
OAK_SHUTTLE: dict | None = _trips_raw.get("oak_shuttle")

# Per-pattern {abbr: (position, offset_seconds)} — parents are unique within a
# pattern (the generator collapses the SFIA wye dwell), so a dict is safe.
_PATTERN_INDEX: list[dict[str, tuple[int, int]]] = [
    {abbr: (position, offset) for position, (abbr, offset) in enumerate(pattern)}
    for pattern in PATTERNS
]

# One representative line per pattern (patterns are shared across at most one
# line in practice; first trip wins) — used by static_ride for unknown trips.
_PATTERN_LINES: dict[int, str] = {}
for _info in TRIPS.values():
    _PATTERN_LINES.setdefault(_info[0], ROUTE_LINES.get(_info[2], "BART"))

# Parent-level direct reachability from the bundled patterns (SPEC-BART §4.2):
# reaches[A] = {stations strictly after A on some pattern}. Drives transfer-
# candidate generation only — every actual leg is realtime-joined.
_REACHES: dict[str, set[str]] = {}
for _pattern in PATTERNS:
    _parents = [abbr for abbr, _ in _pattern]
    for _i, _abbr in enumerate(_parents):
        _REACHES.setdefault(_abbr, set()).update(_parents[_i + 1:])


def get(station_id: str) -> Station | None:
    return _BY_ID.get(station_id)


def by_abbr(abbr: str) -> Station | None:
    return _BY_ABBR.get(abbr)


def parent_of_platform(stop_id: str) -> str | None:
    """RT stop_id ('M16-1') → parent abbr ('EMBR'); unknown ids → None."""
    return PLATFORMS.get(stop_id)


def trip_pattern(trip_id: str) -> dict[str, tuple[int, int]] | None:
    """{abbr: (position, offset_s)} for the trip's stop pattern, or None if
    the trip is unknown to the bundle (GTFS revision rotated, eBART shuttles)."""
    info = TRIPS.get(trip_id)
    return _PATTERN_INDEX[info[0]] if info else None


def trip_line(trip_id: str) -> tuple[str, str]:
    """(line_name, dark_theme_hex); unknown trips/routes → neutral 'BART'."""
    info = TRIPS.get(trip_id)
    line = ROUTE_LINES.get(info[2]) if info else None
    if line is None:
        return "BART", NEUTRAL_LINE_COLOR
    return line, LINE_COLORS[line]


def trip_terminus(trip_id: str) -> str | None:
    """Display terminus = the pattern's last stop (NOT GTFS trip_headsign,
    which is rider-hostile — SPEC-BART §4.4). Returns the station name."""
    info = TRIPS.get(trip_id)
    if info is None:
        return None
    last_abbr = PATTERNS[info[0]][-1][0]
    station = _BY_ABBR.get(last_abbr)
    return station.name if station else None


def reaches(abbr: str) -> set[str]:
    return _REACHES.get(abbr, set())


def static_ride(
    origin_abbr: str,
    destination_abbr: str,
    observed: list[tuple[str, int]],
) -> dict | None:
    """Arrival fallback for trips unknown to the bundle (eBART shuttles, or
    the whole feed after a GTFS rotation): the smallest scheduled
    origin→destination delta across patterns serving the ordered pair —
    BART inter-station times are near-constant across patterns, and min is
    the conservative estimate.

    observed is the trip's RT (parent_abbr, epoch) visits; a pattern only
    qualifies if it shares at least two parents with the observation and they
    appear in the same order — that's the direction filter for unknown trips.
    (Two are required because one stop can't establish a heading: verified in
    the capture, where single-STU Antioch-bound shuttles at PCTR would
    otherwise match westbound patterns.)

    Reach must also be unambiguous: if any consistent pattern serving the
    origin does NOT go on to the destination, the trip may short-turn before
    it (e.g. an SFO-terminating trip projected through to Millbrae) — return
    None rather than risk a phantom arrival.

    Returns {'delta_s', 'line', 'terminus'} or None.
    """
    by_time = [abbr for abbr, _ in sorted(observed, key=lambda pair: pair[1])]
    best: dict | None = None
    for index, pattern in enumerate(_PATTERN_INDEX):
        origin = pattern.get(origin_abbr)
        if origin is None:
            continue
        positions = [pattern[abbr][0] for abbr in by_time if abbr in pattern]
        if len(positions) < 2 or positions != sorted(positions):
            continue
        destination = pattern.get(destination_abbr)
        if destination is None or destination[0] <= origin[0]:
            return None  # a consistent pattern short-turns first — ambiguous
        delta = destination[1] - origin[1]
        if best is None or delta < best["delta_s"]:
            terminus = _BY_ABBR.get(PATTERNS[index][-1][0])
            best = {
                "delta_s": delta,
                "line": _PATTERN_LINES.get(index, "BART"),
                "terminus": terminus.name if terminus else None,
            }
    return best


def transfer_min_s(from_platform: str | None, to_platform: str | None, default: int) -> int:
    """Directed platform-level minimum from GTFS transfers.txt; pairs absent
    from the table (or unknown platforms) use the caller's default."""
    if from_platform is None or to_platform is None:
        return default
    return TRANSFERS.get(from_platform, {}).get(to_platform, default)
