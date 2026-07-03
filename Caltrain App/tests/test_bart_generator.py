"""generate_bart_data.py logic on a synthetic GTFS zip: pattern dedup
round-trips, SFIA-dwell collapse, bus-bridge exclusion, transfer copy, and
shuttle constants (SPEC-BART §4.3, §11 Step 1)."""

from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "generate_bart_data",
    Path(__file__).resolve().parent.parent / "scripts" / "generate_bart_data.py",
)
generate_bart_data = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(generate_bart_data)


def _csv(*rows: str) -> str:
    return "\n".join(rows) + "\n"


def synthetic_zip() -> zipfile.ZipFile:
    """Two parents (AAA, BBB) + a shuttle pair, two identical rail trips (one
    pattern), one wye-style repeated stop, one bus-bridge trip to exclude,
    and shuttle trips 600 s apart."""
    files = {
        "feed_info.txt": _csv(
            "feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,feed_end_date,feed_version",
            "Test,https://example.com,en,20260101,20261231,99",
        ),
        "stops.txt": _csv(
            "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station",
            "AAA,Alpha,37.0,-122.0,1,",
            "BBB,Beta,37.1,-122.1,1,",
            "SHUT,Shuttle End,37.2,-122.2,1,",
            "A-1,Alpha,37.0,-122.0,0,AAA",
            "B-1,Beta,37.1,-122.1,0,BBB",
            "S-1,Shuttle End,37.2,-122.2,0,SHUT",
        ),
        "routes.txt": _csv(
            "route_id,route_short_name,route_long_name,route_type",
            "1,Yellow-S,Alpha to Beta,1",
            "19,Grey-N,Shuttle,1",
            "BB-A,BridgeA,Bus Bridge,3",
        ),
        "trips.txt": _csv(
            "route_id,service_id,trip_id,trip_headsign",
            "1,svc,t1,Beta",
            "1,svc,t2,Beta",
            "1,svc,t3,Beta",
            "19,svc,s1,Shuttle",
            "19,svc,s2,Shuttle",
            "19,svc,s3,Shuttle",
            "BB-A,svc,bus1,Bridge",
        ),
        # t1/t2 share a pattern; t3 has a repeated (wye-style) AAA dwell that
        # must collapse to the same 2-stop pattern shape; bus1 must vanish
        "stop_times.txt": _csv(
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence",
            "t1,06:00:00,06:00:00,A-1,0",
            "t1,06:10:00,06:10:00,B-1,1",
            "t2,07:00:00,07:00:00,A-1,0",
            "t2,07:10:00,07:10:00,B-1,1",
            "t3,08:00:00,08:01:00,A-1,0",
            "t3,08:03:00,08:03:00,A-1,1",
            "t3,08:10:00,08:10:00,B-1,2",
            "s1,06:00:00,06:00:00,B-1,0",
            "s1,06:09:00,06:09:00,S-1,1",
            "s2,06:10:00,06:10:00,B-1,0",
            "s2,06:19:00,06:19:00,S-1,1",
            "s3,06:20:00,06:20:00,B-1,0",
            "s3,06:29:00,06:29:00,S-1,1",
            "bus1,06:00:00,06:00:00,A-1,0",
            "bus1,06:30:00,06:30:00,B-1,1",
        ),
        "transfers.txt": _csv(
            "from_stop_id,to_stop_id,transfer_type,min_transfer_time",
            "A-1,B-1,2,45",
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


def test_generator_builds_patterns_trips_and_constants():
    stations_payload, trips_payload = generate_bart_data.build(synthetic_zip())

    assert stations_payload["feed_version"] == "99"
    assert [s["abbr"] for s in stations_payload["stations"]] == ["AAA", "BBB", "SHUT"]
    assert stations_payload["platforms"] == {"A-1": "AAA", "B-1": "BBB", "S-1": "SHUT"}
    assert stations_payload["stations"][0]["id"] == "alpha"
    assert stations_payload["stations"][0]["lines"] == ["Yellow"]

    trips = trips_payload["trips"]
    patterns = trips_payload["patterns"]
    assert "bus1" not in trips  # bus bridge excluded

    # t1/t2 share one pattern; t3's repeated AAA dwell collapses to it too
    assert trips["t1"][0] == trips["t2"][0] == trips["t3"][0]
    assert patterns[trips["t1"][0]] == [["AAA", 0], ["BBB", 600]]

    # round-trip: rebuild each trip's absolute arrivals and compare to stop_times
    def arrivals(trip_id: str) -> dict[str, int]:
        index, first_arrival, _ = trips[trip_id]
        return {abbr: first_arrival + offset for abbr, offset in patterns[index]}

    assert arrivals("t1") == {"AAA": 6 * 3600, "BBB": 6 * 3600 + 600}
    assert arrivals("t2") == {"AAA": 7 * 3600, "BBB": 7 * 3600 + 600}
    assert arrivals("t3") == {"AAA": 8 * 3600, "BBB": 8 * 3600 + 600}

    assert trips_payload["transfers"] == {"A-1": {"B-1": 45}}

    shuttle = trips_payload["oak_shuttle"]
    assert shuttle["rides"] == {"BBB:SHUT": 540}
    assert shuttle["headway_s"] == 600
