"""GTFS-RT protobuf parsing + BART alert filtering (SPEC-BART §11 Step 1).

Feed facts asserted here (85 entities, median 14 STUs, 99 stop_ids) are the
verified properties of the checked-in 2026-07-02 capture — see
tests/fixtures/bart/README.md. If the fixture is ever re-captured, update
these numbers alongside it.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

import pytest
from app import bart, bart_pairs, bart_stations
from conftest import BART_CAPTURE_NOW
from google.transit import gtfs_realtime_pb2


def test_tripupdate_fixture_parses_to_capture_counts(bart_feed):
    trips = bart_feed["trips"]
    assert len(trips) == 85
    stop_counts = [len(trip["stops"]) for trip in trips]
    assert statistics.median(stop_counts) == 14
    assert max(stop_counts) == 25


def test_every_captured_stop_id_resolves_to_a_platform(bart_feed):
    stop_ids = {stu["stop_id"] for trip in bart_feed["trips"] for stu in trip["stops"]}
    assert len(stop_ids) == 99
    assert all(bart_stations.parent_of_platform(stop_id) for stop_id in stop_ids)


def test_stus_carry_epoch_times_and_delay(bart_feed):
    by_id = {trip["trip_id"]: trip for trip in bart_feed["trips"]}
    first = by_id["1842065"]["stops"][0]
    assert first["arrival"]["time"] > 1_700_000_000
    assert first["arrival"]["delay"] == 91
    # the capture caught a Green-line trip mid-disruption (866 s)
    assert any(
        (stu["arrival"] or {}).get("delay", 0) >= 866
        for trip in bart_feed["trips"]
        for stu in trip["stops"]
    )


def test_unknown_stop_id_is_skipped_never_fatal():
    feed = {"trips": [{"trip_id": "x", "stops": [
        {"stop_id": "NOPE-9", "arrival": {"time": 100, "delay": 0}, "departure": None},
        {"stop_id": "M16-1", "arrival": {"time": 200, "delay": 0}, "departure": None},
    ]}]}
    index = bart_pairs.index_feed(feed)
    assert set(index["x"]) == {"EMBR"}


def test_canceled_trips_and_skipped_stops_are_dropped():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"

    ok = feed.entity.add(id="1")
    ok.trip_update.trip.trip_id = "keep"
    stu = ok.trip_update.stop_time_update.add(stop_id="M16-1")
    stu.arrival.time = 100
    skipped = ok.trip_update.stop_time_update.add(stop_id="M16-2")
    skipped.schedule_relationship = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED

    gone = feed.entity.add(id="2")
    gone.trip_update.trip.trip_id = "drop"
    gone.trip_update.trip.schedule_relationship = gtfs_realtime_pb2.TripDescriptor.CANCELED
    gone.trip_update.stop_time_update.add(stop_id="M16-1").arrival.time = 100

    parsed = bart.parse_trip_updates(feed.SerializeToString())
    assert [trip["trip_id"] for trip in parsed["trips"]] == ["keep"]
    assert [stu["stop_id"] for stu in parsed["trips"][0]["stops"]] == ["M16-1"]


def test_undecodable_feed_raises_value_error():
    with pytest.raises(ValueError):
        bart.parse_trip_updates(b"this is not a protobuf")
    with pytest.raises(ValueError):
        bart.parse_alerts_feed(b"\x00\x01garbage\xff")


# --- alerts ------------------------------------------------------------------


def test_alerts_fixture_header_is_generic_and_description_carries_the_message(bart_alerts_bytes):
    parsed = bart.parse_alerts_feed(bart_alerts_bytes)
    assert len(parsed["alerts"]) == 2
    for alert in parsed["alerts"]:
        assert alert["header"] == "BART.gov Alert"
        assert alert["description"]
        assert alert["periods"] == []


def test_parse_alerts_overrides_generic_header_and_treats_no_period_as_active(bart_alerts_bytes):
    alerts = bart_pairs.parse_alerts(bart.parse_alerts_feed(bart_alerts_bytes), now=BART_CAPTURE_NOW)
    assert len(alerts) == 2  # no periods at all → always active
    for alert in alerts:
        assert alert["header"] != "BART.gov Alert"
        assert alert["description"].startswith(alert["header"][:20])
        assert len(alert["header"]) <= 121
        assert alert["id"].startswith("BSA_")


def test_parse_alerts_sentence_truncates_long_descriptions():
    sentence = "Expect delays between stations tonight. " * 5
    parsed = {"alerts": [{"id": "x", "header": "", "description": sentence.strip(), "periods": []}]}
    [alert] = bart_pairs.parse_alerts(parsed)
    # three full sentences fit inside the ~120-char banner window
    assert alert["header"] == ("Expect delays between stations tonight. " * 3).strip()
    assert alert["header"].endswith(".")


def test_parse_alerts_word_truncates_when_no_sentence_boundary_fits():
    description = "word " * 60
    parsed = {"alerts": [{"id": "x", "header": "", "description": description.strip(), "periods": []}]}
    [alert] = bart_pairs.parse_alerts(parsed)
    assert alert["header"].endswith("…")
    assert len(alert["header"]) <= 121


def test_parse_alerts_filters_by_active_period():
    now = datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    parsed = {"alerts": [
        {"id": "past", "header": "h", "description": "d",
         "periods": [{"start": epoch - 200, "end": epoch - 100}]},
        {"id": "current", "header": "h", "description": "d",
         "periods": [{"start": epoch - 100, "end": epoch + 100}]},
        {"id": "open-ended", "header": "h", "description": "d",
         "periods": [{"start": epoch - 100, "end": None}]},
    ]}
    alerts = bart_pairs.parse_alerts(parsed, now=now)
    assert [alert["id"] for alert in alerts] == ["current", "open-ended"]
    expected_end = datetime.fromtimestamp(epoch + 100, tz=timezone.utc)
    assert alerts[0]["active_period"]["end"] == expected_end.isoformat()
