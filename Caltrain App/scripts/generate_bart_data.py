"""Regenerate data/bart_stations.json and data/bart_trips.json from BART's
static GTFS (SPEC-BART §4).

Usage:
    python3 scripts/generate_bart_data.py            # downloads the GTFS zip
    python3 scripts/generate_bart_data.py --zip P    # use an already-downloaded zip
    python3 scripts/generate_bart_data.py --force    # write even if station count ≠ 50

Re-run when BART rotates the schedule feed (check feed_info.txt feed_version;
v72 expires 2026-08-07). Unknown trip_ids degrade gracefully in the app until
then (SPEC-BART §5.3), so this is maintenance, not an emergency.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import httpx

GTFS_URL = "https://www.bart.gov/dev/schedules/google_transit.zip"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXPECTED_STATION_COUNT = 50


def slugify(name: str) -> str:
    """'Pittsburg/Bay Point' → 'pittsburg_bay_point' (Caltrain id convention)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def line_of(route_short_name: str) -> str:
    """'Yellow-S' → 'Yellow' (§4.4: collapse both directions to the line)."""
    return route_short_name.split("-")[0]


def parse_gtfs_time(value: str) -> int:
    """GTFS clock time → seconds after midnight; may exceed 86400 ('25:10:00')."""
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def read_csv(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with zf.open(name) as fh:
        return list(csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig")))


def build(zf: zipfile.ZipFile) -> tuple[dict, dict]:
    """Return (stations_payload, trips_payload) per SPEC-BART §4.1 / §4.2."""
    feed_version = read_csv(zf, "feed_info.txt")[0]["feed_version"]
    generated_at = date.today().isoformat()

    # --- stops: parent stations + platform → parent map --------------------
    stations_by_abbr: dict[str, dict] = {}
    platforms: dict[str, str] = {}
    for stop in read_csv(zf, "stops.txt"):
        if stop["location_type"] == "1":
            abbr = stop["stop_id"]
            stations_by_abbr[abbr] = {
                "id": slugify(stop["stop_name"]),
                "abbr": abbr,
                "name": stop["stop_name"],
                "lat": float(stop["stop_lat"]),
                "lon": float(stop["stop_lon"]),
                "lines": set(),
            }
        elif stop["parent_station"]:
            platforms[stop["stop_id"]] = stop["parent_station"]

    # --- routes: rail only; bus bridges (route_type 3, BB-*) excluded ------
    rail_route_line: dict[str, str] = {
        route["route_id"]: line_of(route["route_short_name"])
        for route in read_csv(zf, "routes.txt")
        if route["route_type"] == "1"
    }

    trip_route: dict[str, str] = {
        trip["trip_id"]: trip["route_id"]
        for trip in read_csv(zf, "trips.txt")
        if trip["route_id"] in rail_route_line
    }

    # --- stop_times → parent-level (abbr, arrival_seconds) sequences -------
    trip_stops: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    for row in read_csv(zf, "stop_times.txt"):
        trip_id = row["trip_id"]
        if trip_id not in trip_route or not row["arrival_time"]:
            continue
        parent = platforms.get(row["stop_id"])
        if parent is None:
            continue
        trip_stops[trip_id].append(
            (int(row["stop_sequence"]), parent, parse_gtfs_time(row["arrival_time"]))
        )

    # --- dedupe into patterns (§4.2) ----------------------------------------
    patterns: list[list[list]] = []
    pattern_index: dict[tuple, int] = {}
    trips: dict[str, list] = {}
    repeated_parent_trips = 0
    for trip_id, rows in trip_stops.items():
        rows.sort()
        # The SFIA wye reversal is modeled as two consecutive stop_times rows
        # at the same parent (verified feed v72: SFIA only, always adjacent) —
        # keep the first, whose time is the *arrival* the projection needs.
        deduped = [row for i, row in enumerate(rows) if i == 0 or row[1] != rows[i - 1][1]]
        first_arrival = deduped[0][2]
        pattern = tuple((parent, arrival - first_arrival) for _, parent, arrival in deduped)
        parents = [parent for parent, _ in pattern]
        if len(set(parents)) != len(parents):
            repeated_parent_trips += 1
        index = pattern_index.setdefault(pattern, len(patterns))
        if index == len(patterns):
            patterns.append([list(pair) for pair in pattern])
        trips[trip_id] = [index, first_arrival, trip_route[trip_id]]

        for parent in parents:
            station = stations_by_abbr.get(parent)
            if station:
                station["lines"].add(rail_route_line[trip_route[trip_id]])

    # --- OAK shuttle synthesis constants ------------------------------------
    # The airport people-mover never appears in GTFS-RT (verified live
    # 2026-07-02: zero Grey trips in the feed), so the app synthesizes its leg
    # from these. Headway is the p90 gap between consecutive departures and
    # ride time the per-direction max — both conservative by construction.
    grey_routes = {rid for rid, line in rail_route_line.items() if line == "Grey"}
    shuttle_starts: dict[str, list[int]] = defaultdict(list)
    shuttle_rides: dict[str, int] = {}
    for trip_id, rows in trip_stops.items():
        if trip_route[trip_id] not in grey_routes:
            continue
        rows.sort()
        key = f"{rows[0][1]}:{rows[-1][1]}"
        shuttle_starts[key].append(rows[0][2])
        shuttle_rides[key] = max(shuttle_rides.get(key, 0), rows[-1][2] - rows[0][2])
    headways = []
    for starts in shuttle_starts.values():
        starts.sort()
        gaps = sorted(b - a for a, b in zip(starts, starts[1:]) if b - a > 0)
        if gaps:
            headways.append(gaps[int(len(gaps) * 0.9)])
    oak_shuttle = {"headway_s": max(headways), "rides": shuttle_rides} if headways else None

    # --- transfers.txt, platform-level and directed, verbatim seconds ------
    # Feed v72 lists 34 rows but only 30 unique directed platform pairs — a
    # few pairs repeat once per route combination with the same seconds value,
    # so the dict naturally dedupes them.
    transfers: dict[str, dict[str, int]] = defaultdict(dict)
    for row in read_csv(zf, "transfers.txt"):
        if row["from_stop_id"] and row["to_stop_id"] and row["min_transfer_time"]:
            transfers[row["from_stop_id"]][row["to_stop_id"]] = int(row["min_transfer_time"])

    stations = sorted(stations_by_abbr.values(), key=lambda s: s["name"])
    for station in stations:
        station["lines"] = sorted(station["lines"])

    stations_payload = {
        "generated_at": generated_at,
        "source": GTFS_URL,
        "feed_version": feed_version,
        "stations": stations,
        "platforms": platforms,
    }
    trips_payload = {
        "generated_at": generated_at,
        "feed_version": feed_version,
        "patterns": patterns,
        "trips": trips,
        "transfers": dict(transfers),
        "oak_shuttle": oak_shuttle,
    }

    print(
        f"feed v{feed_version}: {len(stations)} stations, {len(platforms)} platforms, "
        f"{len(trips)} trips, {len(patterns)} patterns, "
        f"{sum(len(v) for v in transfers.values())} transfer rows, "
        f"{repeated_parent_trips} trips with a repeated parent"
    )
    return stations_payload, trips_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, help="use a local GTFS zip instead of downloading")
    parser.add_argument("--force", action="store_true", help="write even if station count is unexpected")
    args = parser.parse_args()

    if args.zip:
        raw = args.zip.read_bytes()
    else:
        print(f"downloading {GTFS_URL} …")
        # the URL 307-redirects; redirects MUST be followed (SPEC-BART §1.3)
        raw = httpx.get(GTFS_URL, follow_redirects=True, timeout=60).raise_for_status().content

    stations_payload, trips_payload = build(zipfile.ZipFile(io.BytesIO(raw)))

    count = len(stations_payload["stations"])
    if count != EXPECTED_STATION_COUNT and not args.force:
        print(
            f"refusing to write: expected {EXPECTED_STATION_COUNT} stations, got {count} "
            "(schema drift? rerun with --force to override)",
            file=sys.stderr,
        )
        return 1

    stations_path = DATA_DIR / "bart_stations.json"
    trips_path = DATA_DIR / "bart_trips.json"
    stations_path.write_text(json.dumps(stations_payload, indent=1) + "\n", encoding="utf-8")
    trips_path.write_text(json.dumps(trips_payload, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {stations_path} ({stations_path.stat().st_size // 1024} KB)")
    print(f"wrote {trips_path} ({trips_path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
