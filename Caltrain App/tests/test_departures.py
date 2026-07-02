"""Pair-join logic and payload parsing, against crafted and real payloads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import departures
from conftest import make_visit, payload_of

NOW = datetime(2026, 7, 2, 5, 0, 0, tzinfo=timezone.utc)


def _ts(minutes: float) -> str:
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- pair join ---------------------------------------------------------------

def test_joins_origin_and_destination_by_train_number():
    payload = payload_of(
        make_visit("9101", "70131", aimed_dep=_ts(10), expected_dep=_ts(15)),
        make_visit("9101", "70011", aimed_arr=_ts(50), expected_arr=_ts(55)),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert len(rows) == 1
    row = rows[0]
    assert row["train"] == "9101"
    assert row["delay_seconds"] == 300
    assert row["status"] == "late"
    assert row["arrival"]["expected"].startswith("2026-07-02T05:55")


def test_unknown_train_without_destination_visit_is_excluded():
    # Fake train ids ("9xxx") are unknown to the bundled GTFS, and without a
    # matching DestinationRef the row is dropped — the express-skip filter.
    payload = payload_of(
        make_visit("9101", "70131", aimed_dep=_ts(10)),
        make_visit("9102", "70131", aimed_dep=_ts(12), expected_dep=_ts(12)),
        make_visit("9102", "70011", aimed_arr=_ts(60)),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert [r["train"] for r in rows] == ["9102"]


# --- schedule-based arrival fallback (terminal stops have no realtime visit) --

def test_terminal_arrival_estimated_from_bundled_schedule(monkeypatch):
    from app import schedule

    # NOW is 2026-07-02T05:00Z = 22:00 PT on service date 2026-07-01.
    # trip 9200 scheduled: dep San Carlos NB 22:10 PT, arr SF NB 22:30 PT.
    monkeypatch.setattr(schedule, "_DATA", {"9200": {"70131": 79800, "70011": 81000}})
    payload = payload_of(
        make_visit("9200", "70131", aimed_dep=_ts(10), expected_dep=_ts(15), service_date="2026-07-01"),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert len(rows) == 1
    arrival = rows[0]["arrival"]
    assert arrival["estimated"] is True
    assert arrival["aimed"] == "2026-07-01T22:30:00-07:00"
    # scheduled arrival + the train's current 300s delay
    assert arrival["expected"] == "2026-07-01T22:35:00-07:00"


def test_schedule_says_train_skips_destination(monkeypatch):
    from app import schedule

    monkeypatch.setattr(schedule, "_DATA", {"9200": {"70131": 19800, "70021": 21000}})
    payload = payload_of(
        make_visit("9200", "70131", aimed_dep=_ts(10), expected_dep=_ts(10)),
    )
    assert departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW) == []


def test_unknown_trip_with_matching_destination_ref_kept_without_arrival(monkeypatch):
    from app import schedule

    monkeypatch.setattr(schedule, "_DATA", {})
    payload = payload_of(
        make_visit("9300", "70131", aimed_dep=_ts(10), expected_dep=_ts(10), destination_ref="70011"),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert len(rows) == 1
    assert rows[0]["arrival"] is None


def test_destination_visit_without_times_keeps_row_with_null_arrival():
    payload = payload_of(
        make_visit("9101", "70131", aimed_dep=_ts(10), expected_dep=_ts(10)),
        make_visit("9101", "70011"),  # visit exists, times unresolvable
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert len(rows) == 1
    assert rows[0]["arrival"] is None


def test_null_expected_departure_is_scheduled_only_row():
    payload = payload_of(
        make_visit("9101", "70131", aimed_dep=_ts(10)),
        make_visit("9101", "70011", aimed_arr=_ts(50)),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert rows[0]["status"] == "scheduled"
    assert rows[0]["delay_seconds"] is None
    assert rows[0]["departure"]["expected"] is None


def test_small_delay_is_on_time():
    payload = payload_of(
        make_visit("9101", "70131", aimed_dep=_ts(10), expected_dep=_ts(11)),  # +60s
        make_visit("9101", "70011", aimed_arr=_ts(50)),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert rows[0]["status"] == "on_time"
    assert rows[0]["delay_seconds"] == 60


def test_late_threshold_boundary_is_inclusive():
    payload = payload_of(
        make_visit("9101", "70131", aimed_dep=_ts(10), expected_dep=_ts(12)),  # exactly 120s
        make_visit("9101", "70011", aimed_arr=_ts(50)),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert rows[0]["delay_seconds"] == departures.LATE_THRESHOLD_SECONDS
    assert rows[0]["status"] == "late"


def test_departed_trains_filtered_with_grace_window():
    payload = payload_of(
        make_visit("9101", "70131", aimed_dep=_ts(-5), expected_dep=_ts(-5)),  # long gone
        make_visit("9101", "70011", aimed_arr=_ts(40)),
        make_visit("9102", "70131", aimed_dep=_ts(-0.25), expected_dep=_ts(-0.25)),  # within 30s grace
        make_visit("9102", "70011", aimed_arr=_ts(45)),
    )
    rows = departures.pair_departures(payload, "70131", "70011", limit=4, now=NOW)
    assert [r["train"] for r in rows] == ["9102"]


def test_rows_sorted_by_effective_departure_and_limited():
    visits = []
    for i, train in enumerate(["201", "202", "203"]):
        visits.append(make_visit(train, "70131", aimed_dep=_ts(30 - 10 * i), expected_dep=_ts(30 - 10 * i)))
        visits.append(make_visit(train, "70011", aimed_arr=_ts(90)))
    rows = departures.pair_departures(payload_of(*visits), "70131", "70011", limit=2, now=NOW)
    assert [r["train"] for r in rows] == ["203", "202"]


def test_accepts_siri_wrapper_and_collapsed_single_visit():
    payload = payload_of(
        make_visit("101", "70131", aimed_dep=_ts(10), expected_dep=_ts(10)),
        siri_wrapper=True,
        collapse_single=True,
    )
    index = departures.index_visits(payload)
    assert "101" in index


def test_delivery_as_bare_object_and_as_list_both_parse():
    visit = make_visit("101", "70131", aimed_dep=_ts(10))
    as_obj = {"ServiceDelivery": {"StopMonitoringDelivery": {"MonitoredStopVisit": [visit]}}}
    as_list = {"ServiceDelivery": {"StopMonitoringDelivery": [{"MonitoredStopVisit": [visit]}]}}
    assert departures.index_visits(as_obj) == departures.index_visits(as_list)


# --- real captured fixture ---------------------------------------------------

def test_real_fixture_indexes_and_joins(stopmonitoring_payload):
    payload = stopmonitoring_payload
    index = departures.index_visits(payload)
    assert len(index) >= 5  # multiple live trains at capture time

    # San Antonio NB (70201) → San Francisco NB (70011), just before capture.
    # SF is these trains' terminal stop: StopMonitoring carries NO visit for
    # it (verified 2026-07-01), so arrivals must come from the bundled GTFS.
    rows = departures.pair_departures(payload, "70201", "70011", limit=10, now=NOW)
    assert rows, "expected at least one NB train from San Antonio to SF in the fixture"
    for row in rows:
        assert row["arrival"] is not None
        assert row["arrival"]["estimated"] is True
        assert row["arrival"]["aimed"] is not None
        assert row["status"] in {"late", "on_time", "scheduled"}
    times = [row["departure"]["expected"] or row["departure"]["aimed"] for row in rows]
    assert times == sorted(times)

    # A mid-route pair: the soonest train is inside the feed's ~90-min visit
    # horizon so its arrival joins from realtime; later trains may fall past
    # the horizon and get schedule-estimated arrivals — both are valid.
    mid_rows = departures.pair_departures(payload, "70201", "70021", limit=10, now=NOW)
    assert mid_rows
    assert "estimated" not in mid_rows[0]["arrival"]


# --- train types -------------------------------------------------------------

def test_train_type_normalization():
    assert departures.train_type("Local Weekday") == "Local"
    assert departures.train_type("Local Weekend") == "Local"
    assert departures.train_type("LOC") == "Local"
    assert departures.train_type("Limited") == "Limited"
    assert departures.train_type("LIM") == "Limited"
    assert departures.train_type("EXP") == "Express"
    assert departures.train_type("Express") == "Express"
    assert departures.train_type("SCC") == "South County"
    assert departures.train_type("South County") == "South County"
    assert departures.train_type("Mystery Line") == "Mystery Line"  # passthrough
    assert departures.train_type(None) == "Train"
