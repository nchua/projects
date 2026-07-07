"""Canceled-trip rows, BART only (SPEC-V2 §5), built against the synthetic
fixture — zero CANCELED entities exist in any live capture (⚠ VERIFY at the
next real disruption). Fixture entities: A=1842225 canceled/no-STUs (18:03),
B=1951714 canceled/with-STUs (18:05), C=1842289 normal (18:11),
D=9999999 canceled/unknown-to-bundle. Service day 2026-07-06."""

from __future__ import annotations

from datetime import datetime, timezone

from app import bart, bart_pairs, bart_stations
from conftest import FIXTURES
from tests.test_bart_pairs import rows_for

PT = bart_pairs.schedule.PACIFIC
ANCHOR = int(datetime(2026, 7, 6, 12, 0, tzinfo=PT).timestamp()) - 12 * 3600
FIXTURE_NOW = datetime.fromtimestamp(ANCHOR + 18 * 3600, tz=timezone.utc)  # 6:00 PM PT


def synthetic_feed() -> dict:
    return bart.parse_trip_updates(
        (FIXTURES / "bart" / "tripupdate_canceled_synthetic.pb").read_bytes()
    )


def test_parse_splits_canceled_trips_from_live_ones():
    feed = synthetic_feed()
    assert [t["trip_id"] for t in feed["trips"]] == ["1842289"]
    assert {t["trip_id"] for t in feed["canceled_trips"]} == {"1842225", "1951714", "9999999"}
    # canceled trips never reach the join index → can't leak into itineraries
    assert "1842225" not in bart_pairs.index_feed(feed)


def test_real_capture_has_no_canceled_trips(bart_tripupdate_bytes):
    feed = bart.parse_trip_updates(bart_tripupdate_bytes)
    assert feed["canceled_trips"] == []


def test_canceled_rows_interleave_with_live_rows():
    rows = rows_for(synthetic_feed(), "embarcadero", "walnut_creek", now=FIXTURE_NOW)
    assert [row["status"] for row in rows] == ["canceled", "canceled", "on_time"]
    assert [row["trip"] for row in rows] == ["1842225", "1951714", "1842289"]
    for row in rows[:2]:
        assert row["delay_seconds"] is None
        assert row["departure"]["expected"] is None
        assert row["arrival"]["expected"] is None


def test_no_stu_canceled_row_renders_bundled_schedule():
    rows = rows_for(synthetic_feed(), "embarcadero", "walnut_creek", now=FIXTURE_NOW)
    row_a = rows[0]  # 1842225: no STUs kept → bundle times on the service day
    pattern = bart_stations.trip_pattern("1842225")
    first_arrival = bart_stations.TRIPS["1842225"][1]
    expected_dep = ANCHOR + first_arrival + pattern["EMBR"][1]
    assert datetime.fromisoformat(row_a["departure"]["aimed"]).timestamp() == expected_dep
    assert row_a["arrival"]["estimated"] is True
    assert row_a["headsign"].startswith("to ")


def test_with_stu_canceled_row_uses_the_feed_times():
    rows = rows_for(synthetic_feed(), "embarcadero", "walnut_creek", now=FIXTURE_NOW)
    row_b = rows[1]  # 1951714 kept its STUs → feed epochs, arrival not estimated
    feed = synthetic_feed()
    stus = next(t for t in feed["canceled_trips"] if t["trip_id"] == "1951714")["stops"]
    assert datetime.fromisoformat(row_b["departure"]["aimed"]).timestamp() == stus[0]["departure"]["time"]
    assert "estimated" not in row_b["arrival"]


def test_unknown_canceled_trip_is_suppressed():
    rows = rows_for(synthetic_feed(), "embarcadero", "walnut_creek", now=FIXTURE_NOW, limit=10)
    assert "9999999" not in [row["trip"] for row in rows]


def test_canceled_rows_are_additive_to_the_limit():
    # limit=1 selects one live row; both canceled rows still appear (§5.4)
    rows = rows_for(synthetic_feed(), "embarcadero", "walnut_creek", now=FIXTURE_NOW, limit=1)
    assert [row["status"] for row in rows] == ["canceled", "canceled", "on_time"]


def test_canceled_rows_expire_off_the_board():
    later = datetime.fromtimestamp(ANCHOR + 18 * 3600 + 600, tz=timezone.utc)  # 6:10 PM
    rows = rows_for(synthetic_feed(), "embarcadero", "walnut_creek", now=later)
    assert [row["status"] for row in rows] == ["on_time"]


def test_canceled_row_absent_for_pairs_the_trip_never_served():
    # direction filter: WCRK→EMBR is the reverse of every fixture trip
    rows = rows_for(synthetic_feed(), "walnut_creek", "embarcadero", now=FIXTURE_NOW, limit=10)
    assert all(row["status"] != "canceled" for row in rows)


def test_past_midnight_cancellation_anchors_to_the_previous_service_day():
    # a canceled trip with a 24:xx+ static time queried at 00:45 AM must
    # anchor to yesterday's service day (SPEC-V2 §5.3 / §4.3 cutover)
    best = None
    for trip_id, (p_idx, first_arr, _route) in bart_stations.TRIPS.items():
        index = bart_stations._PATTERN_INDEX[p_idx]
        origin, dest = index.get("EMBR"), index.get("MLBR")
        if origin and dest and origin[0] < dest[0]:
            dep = first_arr + origin[1]
            if dep >= 86400 and (best is None or dep > best[1]):
                best = (trip_id, dep)
    assert best is not None, "bundle has no past-midnight EMBR→MLBR trip"
    trip_id, dep_s = best

    feed = {"trips": [], "canceled_trips": [{"trip_id": trip_id, "stops": []}]}
    now = datetime.fromtimestamp(ANCHOR + dep_s - 300, tz=timezone.utc)  # ~00:xx AM next day
    assert now.astimezone(PT).hour < 3  # we really are past midnight, pre-cutover
    rows = bart_pairs.pair_departures(
        feed, bart_stations.get("embarcadero"), bart_stations.get("millbrae"), 4, now=now
    )
    canceled = [row for row in rows if row["status"] == "canceled"]
    assert canceled
    rendered = datetime.fromisoformat(canceled[0]["departure"]["aimed"]).timestamp()
    assert rendered == ANCHOR + dep_s  # yesterday's anchor, not today's