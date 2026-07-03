"""BART pair-join logic against the captured feed + synthesized feeds
(SPEC-BART §5, §11 Step 1)."""

from __future__ import annotations

from datetime import datetime, timezone

from app import bart_pairs, bart_stations
from conftest import BART_CAPTURE_NOW

NOW_EPOCH = int(BART_CAPTURE_NOW.timestamp())


def rows_for(feed: dict, origin: str, destination: str, limit: int = 4, now: datetime | None = None):
    return bart_pairs.pair_departures(
        feed, bart_stations.get(origin), bart_stations.get(destination), limit,
        now or BART_CAPTURE_NOW,
    )


def dep_epoch(row: dict) -> float:
    return datetime.fromisoformat(row["departure"]["expected"]).timestamp()


def arr_epoch(row: dict) -> float:
    return datetime.fromisoformat(row["arrival"]["expected"]).timestamp()


def platform_of(abbr: str) -> str:
    return sorted(p for p, parent in bart_stations.PLATFORMS.items() if parent == abbr)[0]


def find_trip(from_abbr: str, to_abbr: str, exclude_abbr: str | None = None) -> str:
    """A bundled trip whose pattern serves from→to in order (optionally
    avoiding patterns that also contain exclude_abbr)."""
    for trip_id in bart_stations.TRIPS:
        pattern = bart_stations.trip_pattern(trip_id)
        origin, destination = pattern.get(from_abbr), pattern.get(to_abbr)
        if origin is None or destination is None or destination[0] <= origin[0]:
            continue
        if exclude_abbr is not None and exclude_abbr in pattern:
            continue
        return trip_id
    raise AssertionError(f"no bundled trip serves {from_abbr}→{to_abbr}")


def make_stu(abbr: str, arr: int | None, dep: int | None, delay: int = 0, stop_id: str | None = None) -> dict:
    return {
        "stop_id": stop_id or platform_of(abbr),
        "arrival": {"time": arr, "delay": delay} if arr is not None else None,
        "departure": {"time": dep, "delay": delay} if dep is not None else None,
    }


# --- direct joins on the captured feed ---------------------------------------


def test_realtime_pair_join_embarcadero_to_walnut_creek(bart_feed):
    rows = rows_for(bart_feed, "embarcadero", "walnut_creek")
    assert 0 < len(rows) <= 4
    for row in rows:
        assert row["line"] == "Yellow"
        assert row["line_color"] == "#ffe14d"
        assert row["headsign"].startswith("to ")
        assert "estimated" not in row["arrival"]  # realtime at both ends (§5.2-1)
        assert arr_epoch(row) > dep_epoch(row)
        assert "legs" not in row and "transfers" not in row
    assert [dep_epoch(r) for r in rows] == sorted(dep_epoch(r) for r in rows)


def test_truncated_terminal_projects_estimated_arrival(bart_feed):
    rows = rows_for(bart_feed, "embarcadero", "antioch")
    assert rows
    for row in rows:
        assert row["arrival"]["estimated"] is True  # §5.2-2 delta projection
        assert arr_epoch(row) > dep_epoch(row)  # sanity: never arrive before departing


def test_wye_pair_serves_both_directions(bart_feed):
    # SFIA↔MLBR: same line both ways — compass direction would lie (§5.1-2)
    assert rows_for(bart_feed, "millbrae", "san_francisco_international_airport")
    assert rows_for(bart_feed, "san_francisco_international_airport", "millbrae")


def test_delay_thresholds_and_status(bart_feed):
    rows = [
        row
        for origin, destination in (
            ("daly_city", "berryessa_north_san_jose"),
            ("embarcadero", "walnut_creek"),
        )
        for row in rows_for(bart_feed, origin, destination, limit=10)
    ]
    assert any(row["status"] == "late" for row in rows)  # the 866 s Green disruption
    for row in rows:
        if row["status"] == "late":
            assert row["delay_seconds"] >= 120
        elif row["status"] == "on_time":
            assert (row["delay_seconds"] or 0) < 120


def test_limit_is_respected(bart_feed):
    assert len(rows_for(bart_feed, "embarcadero", "walnut_creek", limit=2)) == 2


# --- direct joins on synthesized feeds ----------------------------------------


def test_short_turn_trip_is_excluded():
    # a trip whose pattern lacks the destination must not appear (§5.2-3):
    # Green-line trips serve EMBR but never WCRK
    green = find_trip("EMBR", "COLS", exclude_abbr="WCRK")
    yellow = find_trip("EMBR", "WCRK")
    feed = {"trips": [
        {"trip_id": green, "stops": [make_stu("EMBR", 1000, 1010)]},
        {"trip_id": yellow, "stops": [make_stu("EMBR", 1000, 1200)]},
    ]}
    now = datetime.fromtimestamp(1000, tz=timezone.utc)
    rows = rows_for(feed, "embarcadero", "walnut_creek", now=now)
    assert [row["trip"] for row in rows] == [yellow]
    assert rows[0]["arrival"]["estimated"] is True


def test_departure_grace_window():
    yellow = find_trip("EMBR", "WCRK")
    feed = {"trips": [{"trip_id": yellow, "stops": [make_stu("EMBR", None, 1000)]}]}
    fresh = datetime.fromtimestamp(1020, tz=timezone.utc)  # 20 s after departure: kept
    gone = datetime.fromtimestamp(1060, tz=timezone.utc)  # 60 s after: dropped
    assert rows_for(feed, "embarcadero", "walnut_creek", now=fresh)
    assert rows_for(feed, "embarcadero", "walnut_creek", now=gone) == []


def test_wrong_direction_falls_out_of_arrival_after_departure():
    yellow = find_trip("EMBR", "WCRK")
    feed = {"trips": [{"trip_id": yellow, "stops": [
        make_stu("EMBR", 1000, 1010),
        make_stu("WCRK", 3000, 3010),
    ]}]}
    now = datetime.fromtimestamp(990, tz=timezone.utc)
    assert rows_for(feed, "embarcadero", "walnut_creek", now=now)
    # same feed, reversed pair: WCRK departure exists but EMBR arrival precedes it
    assert rows_for(feed, "walnut_creek", "embarcadero", now=now) == []


def test_missing_delay_defaults_to_on_time():
    yellow = find_trip("EMBR", "WCRK")
    feed = {"trips": [{"trip_id": yellow, "stops": [
        {"stop_id": platform_of("EMBR"), "arrival": None,
         "departure": {"time": 1000, "delay": None}},
    ]}]}
    now = datetime.fromtimestamp(900, tz=timezone.utc)
    [row] = rows_for(feed, "embarcadero", "walnut_creek", now=now)
    assert row["delay_seconds"] is None
    assert row["status"] == "on_time"  # times present; only the delay is unknown


# --- unknown trips (eBART shuttles / GTFS rotation) ---------------------------


def test_unknown_trip_included_when_destination_is_in_rt_stus(bart_feed):
    # trip 663 family: ANTC→PCTR with both STUs realtime (§5.2-4 case 1)
    rows = rows_for(bart_feed, "antioch", "pittsburg_center")
    assert rows
    assert all("estimated" not in row["arrival"] for row in rows)


def test_unknown_trip_projects_via_static_ride_beyond_its_stus(bart_feed):
    # ANTC→EMBR: shuttle STUs end at PCTR; the static Yellow through-pattern
    # supplies the delta, the line, and the terminus (§5.2-4 amendment)
    rows = rows_for(bart_feed, "antioch", "embarcadero")
    assert rows
    for row in rows:
        assert row["arrival"]["estimated"] is True
        assert row["line"] == "Yellow"
        assert row["headsign"].startswith("to ")


def test_static_ride_rejects_ambiguous_reach():
    # an unknown trip observed EMBR→SFIA might be an SFO short-turn OR a
    # through-to-Millbrae trip — feed v72 has consistent patterns of both
    # kinds, so projecting a Millbrae arrival would risk a phantom row
    embr, sfia = platform_of("EMBR"), platform_of("SFIA")
    feed = {"trips": [{"trip_id": "not-in-bundle", "stops": [
        make_stu("EMBR", 1000, 1010, stop_id=embr),
        make_stu("SFIA", 3000, 3010, stop_id=sfia),
    ]}]}
    now = datetime.fromtimestamp(990, tz=timezone.utc)
    assert rows_for(feed, "embarcadero", "millbrae", now=now) == []
    # …but the realtime-covered leg of the same trip still resolves (§5.2-4 case 1)
    assert rows_for(feed, "embarcadero", "san_francisco_international_airport", now=now)


def test_single_stu_unknown_trips_cannot_establish_direction(bart_feed):
    # eastbound shuttles at PCTR appear as single-STU trips (656 family) —
    # they must not leak into westbound results, and with no second observed
    # stop they must not appear at all
    single_stu_ids = {
        trip["trip_id"]
        for trip in bart_feed["trips"]
        if bart_stations.trip_pattern(trip["trip_id"]) is None and len(trip["stops"]) == 1
    }
    assert "656" in single_stu_ids
    west = rows_for(bart_feed, "pittsburg_center", "walnut_creek", limit=10)
    assert west
    assert single_stu_ids.isdisjoint({row["trip"] for row in west})
