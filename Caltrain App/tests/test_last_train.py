"""Last-train-tonight badge (SPEC-V2 §4): static pair-maxima, the service-day
cutover, and the badge conditions on both agencies."""

from __future__ import annotations

from datetime import datetime, timezone

from app import bart_stations, schedule
from app.departures import pair_departures
from conftest import make_visit, payload_of
from tests.test_bart_pairs import make_stu, rows_for

PT = schedule.PACIFIC


# --- pinned pair-maxima (SPEC-V2 §4.2 — move only when the bundles rotate) ----


def test_caltrain_pair_maxima_match_spec():
    assert schedule.pair_max_service_s("70131", "70011") // 60 == 25 * 60 + 51  # SanCarlos→SF
    assert schedule.pair_max_service_s("70012", "70132") // 60 == 24 * 60 + 5  # SF→SanCarlos
    assert schedule.pair_max_service_s("70061", "70011") // 60 == 26 * 60 + 8  # Millbrae→SF


def test_bart_pair_maxima_match_spec():
    assert bart_stations.pair_max_service_s("EMBR", "WCRK") // 60 == 24 * 60 + 32
    assert bart_stations.pair_max_service_s("WCRK", "EMBR") // 60 == 24 * 60 + 29
    assert bart_stations.pair_max_service_s("MLBR", "EMBR") // 60 == 20 * 60 + 54


def test_pair_max_none_when_no_bundled_trip_serves_the_pair():
    assert schedule.pair_max_service_s("70011", "70012") is None  # same station, both dirs
    assert bart_stations.pair_max_service_s("OAKL", "ANTC") is None  # shuttle appendage


# --- service-day seconds (SPEC-V2 §4.3) ---------------------------------------


def test_cutover_maps_late_night_into_the_previous_service_day():
    late = datetime(2026, 7, 7, 2, 59, tzinfo=PT)  # 2:59 AM → 26:59 of July 6 service
    assert schedule.service_day_seconds(late) == 26 * 3600 + 59 * 60
    morning = datetime(2026, 7, 7, 3, 1, tzinfo=PT)  # 3:01 AM → new service day
    assert schedule.service_day_seconds(morning) == 3 * 3600 + 60
    noon = datetime(2026, 7, 7, 12, 0, tzinfo=PT)
    assert schedule.service_day_seconds(noon) == 12 * 3600


# --- Caltrain badge ------------------------------------------------------------


def _last_train_and_visits(origin_stop: str, destination_stop: str):
    """The bundled trip that IS the pair's static max, and its clock time."""
    best = None
    for trip_id, stops in schedule._DATA.items():
        origin = stops.get(origin_stop)
        destination = stops.get(destination_stop)
        if origin is not None and destination is not None and origin < destination:
            if best is None or origin > best[1]:
                best = (trip_id, origin, destination)
    assert best is not None
    return best


def _ct_rows(dep_service_s: int, trip_id: str, limit: int = 4):
    """One SF→San Carlos visit whose aimed departure sits at dep_service_s
    (service-day seconds) on the 2026-07-06 service day."""
    anchor = datetime(2026, 7, 6, 12, 0, tzinfo=PT).timestamp() - 12 * 3600
    dep = datetime.fromtimestamp(anchor + dep_service_s, tz=timezone.utc)
    arr = datetime.fromtimestamp(anchor + dep_service_s + 3000, tz=timezone.utc)
    payload = payload_of(
        make_visit(trip_id, "70012", aimed_dep=dep.isoformat(), expected_dep=dep.isoformat(),
                   service_date="2026-07-06"),
        make_visit(trip_id, "70132", aimed_arr=arr.isoformat(), expected_arr=arr.isoformat(),
                   service_date="2026-07-06"),
    )
    now = datetime.fromtimestamp(anchor + dep_service_s - 600, tz=timezone.utc)
    return pair_departures(payload, "70012", "70132", limit, now=now)


def test_ct_final_row_within_epsilon_of_pair_max_is_badged():
    trip_id, origin_s, _ = _last_train_and_visits("70012", "70132")
    [row] = _ct_rows(origin_s, trip_id)
    assert row["last_train"] is True


def test_ct_row_far_from_pair_max_is_not_badged():
    trip_id, origin_s, _ = _last_train_and_visits("70012", "70132")
    [row] = _ct_rows(origin_s - 3600, trip_id)  # an hour before the last train
    assert "last_train" not in row


def test_ct_no_badge_when_rows_reach_the_limit():
    trip_id, origin_s, _ = _last_train_and_visits("70012", "70132")
    [row] = _ct_rows(origin_s, trip_id, limit=1)  # feed not exhausted below limit
    assert "last_train" not in row


def test_ct_unknown_trip_suppresses_the_badge():
    # post-GTFS-rotation degrade (§4.4-3): the row survives via the realtime
    # destination visit, but the badge must not fire
    trip_id, origin_s, _ = _last_train_and_visits("70012", "70132")
    assert schedule.trip_stops("99999") is None
    [row] = _ct_rows(origin_s, "99999")
    assert "last_train" not in row


# --- BART badge -----------------------------------------------------------------


def _ba_last_trip(origin_abbr: str, destination_abbr: str):
    best = None
    for trip_id, (p_idx, first_arr, _route) in bart_stations.TRIPS.items():
        index = bart_stations._PATTERN_INDEX[p_idx]
        origin = index.get(origin_abbr)
        destination = index.get(destination_abbr)
        if origin and destination and origin[0] < destination[0]:
            dep = first_arr + origin[1]
            if best is None or dep > best[1]:
                best = (trip_id, dep)
    assert best is not None
    return best


def _ba_rows(dep_service_s: int, trip_id: str, limit: int = 4):
    anchor = int(datetime(2026, 7, 6, 12, 0, tzinfo=PT).timestamp()) - 12 * 3600
    dep = anchor + dep_service_s
    feed = {"trips": [{"trip_id": trip_id, "stops": [
        make_stu("EMBR", dep - 30, dep),
        make_stu("WCRK", dep + 2100, dep + 2130),
    ]}]}
    now = datetime.fromtimestamp(dep - 600, tz=timezone.utc)
    return rows_for(feed, "embarcadero", "walnut_creek", limit=limit, now=now)


def test_ba_final_row_within_epsilon_of_pair_max_is_badged():
    trip_id, dep_s = _ba_last_trip("EMBR", "WCRK")
    [row] = _ba_rows(dep_s, trip_id)
    assert row["last_train"] is True
    assert dep_s > 86400  # the last train really is a past-midnight departure


def test_ba_midday_row_is_not_badged():
    trip_id, dep_s = _ba_last_trip("EMBR", "WCRK")
    [row] = _ba_rows(dep_s - 7200, trip_id)
    assert "last_train" not in row


def test_ba_unknown_trip_suppresses_the_badge():
    _, dep_s = _ba_last_trip("EMBR", "WCRK")
    [row] = _ba_rows(dep_s, "9999999")  # resolves via RT STUs, badge suppressed
    assert "last_train" not in row


def test_ba_no_badge_when_rows_reach_the_limit():
    trip_id, dep_s = _ba_last_trip("EMBR", "WCRK")
    [row] = _ba_rows(dep_s, trip_id, limit=1)
    assert "last_train" not in row
