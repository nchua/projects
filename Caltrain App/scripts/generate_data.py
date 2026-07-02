"""Regenerate the bundled GTFS-derived data files:

  data/stations.json       station registry (ids, names, coords, stop codes)
  data/trip_arrivals.json  {trip_id: {stop_code: arrival_seconds_since_midnight}}

trip_arrivals fills the gap where 511's realtime feeds carry no arrival time:
StopMonitoring omits arrival-only (terminal) stops and TripUpdates only
carries the next stop (both verified live 2026-07-01). Trips are looked up
by realtime-supplied trip_id only — this is NOT a schedule engine.

Usage:
    python3 scripts/generate_data.py            # downloads the GTFS zip
    python3 scripts/generate_data.py --zip path/to/caltrain-ca-us.zip

Run manually when Caltrain changes its schedule (trip_ids rotate with GTFS
revisions — unknown trip_ids degrade gracefully to an em-dash arrival);
outputs are checked in so the deployed app never touches GTFS at runtime.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

GTFS_URL = "https://data.trilliumtransit.com/gtfs/caltrain-ca-us/caltrain-ca-us.zip"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATIONS_OUTPUT = DATA_DIR / "stations.json"
ARRIVALS_OUTPUT = DATA_DIR / "trip_arrivals.json"

# Caltrain platform stop codes: 70011 (SF NB) .. 70322 (Gilroy SB).
# NB codes end in 1, SB in 2.
PLATFORM_CODE = re.compile(r"^70\d{3}$")
# Stanford Stadium is game-day only — excluded per SPEC §4.3. Its platforms
# currently use non-70xxx ids, but skip its historical codes explicitly in
# case a future GTFS revision reintroduces them.
STANFORD_STADIUM_CODES = {"70181", "70182"}
NAME_SUFFIXES = (" Caltrain Station", " Caltrain", " Station")


def slugify(name: str) -> str:
    """'San Jose Diridon' -> 'san_jose_diridon'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def clean_name(stop_name: str) -> str:
    """Strip GTFS naming suffixes: 'San Carlos Station' -> 'San Carlos'."""
    for suffix in NAME_SUFFIXES:
        if stop_name.endswith(suffix):
            return stop_name[: -len(suffix)]
    return stop_name


def load_csv(zip_bytes: bytes, name: str) -> list[dict[str, str]]:
    """Read one CSV file's rows from the GTFS zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        with zf.open(name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8-sig")
            return list(csv.DictReader(text))


def gtfs_seconds(hms: str) -> int:
    """GTFS 'HH:MM:SS' → seconds since midnight; hours may exceed 24."""
    hours, minutes, seconds = (int(part) for part in hms.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def build_trip_arrivals(
    stop_times: list[dict[str, str]],
    stops: list[dict[str, str]],
) -> dict[str, dict[str, int]]:
    """{trip_id: {platform_stop_code: arrival_seconds}} for 70xxx stops.

    stop_times references stops by stop_id; the app joins on stop_code (what
    the 511 realtime feed uses). They are currently equal for platforms, but
    translate explicitly so a GTFS revision changing stop_ids fails loudly
    here instead of silently breaking the arrival fallback at runtime.
    """
    code_by_id = {s["stop_id"]: s.get("stop_code", "") for s in stops}
    arrivals: dict[str, dict[str, int]] = {}
    for row in stop_times:
        code = code_by_id.get(row["stop_id"], "")
        if not PLATFORM_CODE.match(code) or code in STANFORD_STADIUM_CODES:
            continue
        arrivals.setdefault(row["trip_id"], {})[code] = gtfs_seconds(row["arrival_time"])
    if not arrivals:
        raise SystemExit("No platform stop_times matched — GTFS structure changed?")
    return arrivals


def build_stations(stops: list[dict[str, str]]) -> list[dict[str, object]]:
    """Group NB/SB platforms by parent station and emit station records."""
    parents = {s["stop_id"]: s for s in stops if s["location_type"] == "1"}

    platforms: dict[str, dict[str, str]] = {}
    for s in stops:
        code = s.get("stop_code", "")
        parent = s.get("parent_station", "")
        if not (PLATFORM_CODE.match(code) and parent in parents):
            continue
        if code in STANFORD_STADIUM_CODES:
            continue
        by_dir = platforms.setdefault(parent, {})
        if code.endswith("1"):
            by_dir["nb"] = code
        elif code.endswith("2"):
            by_dir["sb"] = code

    stations = []
    for parent_id, codes in platforms.items():
        if "nb" not in codes or "sb" not in codes:
            continue  # not a regular bidirectional station
        parent = parents[parent_id]
        name = clean_name(parent["stop_name"])
        stations.append(
            {
                "id": slugify(name),
                "name": name,
                "lat": round(float(parent["stop_lat"]), 6),
                "lon": round(float(parent["stop_lon"]), 6),
                "stop_nb": codes["nb"],
                "stop_sb": codes["sb"],
                "order": (int(codes["nb"]) - 70011) // 10,
            }
        )
    stations.sort(key=lambda s: s["order"])
    return stations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", help="Use a local GTFS zip instead of downloading")
    args = parser.parse_args()

    if args.zip:
        zip_bytes = Path(args.zip).read_bytes()
    else:
        print(f"Downloading {GTFS_URL} …")
        with urllib.request.urlopen(GTFS_URL) as resp:
            zip_bytes = resp.read()

    stops = load_csv(zip_bytes, "stops.txt")
    stations = build_stations(stops)
    payload = {
        "generated_at": date.today().isoformat(),
        "source": GTFS_URL,
        "stations": stations,
    }
    STATIONS_OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(stations)} stations to {STATIONS_OUTPUT}")

    arrivals = build_trip_arrivals(load_csv(zip_bytes, "stop_times.txt"), stops)
    ARRIVALS_OUTPUT.write_text(json.dumps(arrivals, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {len(arrivals)} trips to {ARRIVALS_OUTPUT}")


if __name__ == "__main__":
    main()
