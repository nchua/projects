"""Endpoint-level BART behavior: agency routing, response shapes, health,
merged alerts (SPEC-BART §7)."""

from __future__ import annotations

import time

import httpx
import respx
from app.main import app
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2
from tests.test_bart_pairs import find_trip, platform_of

client = TestClient(app)

TU_URL = "https://api.bart.gov/gtfsrt/tripupdate.aspx"
BA_ALERTS_URL = "https://api.bart.gov/gtfsrt/alerts.aspx"
CT_ALERTS_URL = "https://api.511.org/transit/servicealerts"


def _bom(payload: dict) -> bytes:
    import json

    return b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")


def live_feed_bytes() -> bytes:
    """A tiny valid feed with epochs relative to the real clock, so endpoint
    tests are deterministic regardless of when they run."""
    now = int(time.time())
    trip_id = find_trip("EMBR", "WCRK")
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add(id="1")
    entity.trip_update.trip.trip_id = trip_id
    for stop_id, offset in ((platform_of("EMBR"), 300), (platform_of("WCRK"), 2400)):
        stu = entity.trip_update.stop_time_update.add(stop_id=stop_id)
        stu.arrival.time = now + offset
        stu.arrival.delay = 0
        stu.departure.time = now + offset + 20
        stu.departure.delay = 0
    return feed.SerializeToString()


def alert_feed_bytes(description: str = "Major delays systemwide due to an earlier problem.") -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add(id="BSA_TEST")
    translation = entity.alert.header_text.translation.add()
    translation.text, translation.language = "BART.gov Alert", "en"
    translation = entity.alert.description_text.translation.add()
    translation.text, translation.language = description, "en"
    return feed.SerializeToString()


def test_stations_payload_gains_bart_without_touching_caltrain():
    body = client.get("/api/stations").json()
    assert len(body["stations"]) == 30  # untouched original key
    assert len(body["bart_stations"]) == 50
    sample = body["bart_stations"][0]
    assert {"id", "abbr", "name", "lat", "lon", "lines"} <= set(sample)


@respx.mock
def test_bart_departures_endpoint_shape():
    respx.get(TU_URL).mock(return_value=httpx.Response(200, content=live_feed_bytes()))
    body = client.get(
        "/api/departures", params={"agency": "ba", "origin": "embarcadero", "destination": "walnut_creek"}
    ).json()
    assert body["agency"] == "ba"
    assert body["origin"] == {"id": "embarcadero", "abbr": "EMBR", "name": "Embarcadero"}
    assert body["destination"]["abbr"] == "WCRK"
    assert "direction" not in body  # meaningless on a branching network
    assert body["stale"] is False
    [row] = body["departures"]
    assert row["line"] == "Yellow"
    assert row["line_color"] == "#ffe14d"
    assert row["status"] == "on_time"
    assert row["departure"]["expected"] < row["arrival"]["expected"]


def test_unknown_agency_is_rejected():
    body = client.get(
        "/api/departures", params={"agency": "xx", "origin": "a", "destination": "b"}
    )
    assert body.status_code == 400
    assert body.json()["error"]["code"] == "unknown_agency"


def test_unknown_bart_station_and_same_station_are_rejected():
    error = client.get(
        "/api/departures", params={"agency": "ba", "origin": "nope", "destination": "antioch"}
    )
    assert error.status_code == 400
    assert error.json()["error"]["code"] == "unknown_station"

    error = client.get(
        "/api/departures", params={"agency": "ba", "origin": "antioch", "destination": "antioch"}
    )
    assert error.status_code == 400
    assert error.json()["error"]["code"] == "same_station"


def test_caltrain_station_ids_do_not_resolve_for_bart():
    error = client.get(
        "/api/departures", params={"agency": "ba", "origin": "san_carlos", "destination": "antioch"}
    )
    assert error.status_code == 400


@respx.mock
def test_bart_alerts_endpoint():
    respx.get(BA_ALERTS_URL).mock(return_value=httpx.Response(200, content=alert_feed_bytes()))
    body = client.get("/api/alerts", params={"agency": "ba"}).json()
    assert body["agency"] == "ba"
    [alert] = body["alerts"]
    assert alert["id"] == "BSA_TEST"
    assert alert["header"].startswith("Major delays")


@respx.mock
def test_all_alerts_merges_and_tags_both_feeds(servicealerts_bytes):
    respx.get(url__startswith=CT_ALERTS_URL).mock(
        return_value=httpx.Response(200, content=servicealerts_bytes)
    )
    respx.get(BA_ALERTS_URL).mock(return_value=httpx.Response(200, content=alert_feed_bytes()))
    body = client.get("/api/alerts", params={"agency": "all"}).json()
    assert body["agency"] == "all"
    assert body["stale"] is False
    agencies = {alert["agency"] for alert in body["alerts"]}
    assert "ba" in agencies
    assert all(set(alert) >= {"id", "header", "description", "agency"} for alert in body["alerts"])


@respx.mock
def test_all_alerts_survives_one_feed_being_down(servicealerts_bytes):
    respx.get(url__startswith=CT_ALERTS_URL).mock(
        return_value=httpx.Response(200, content=servicealerts_bytes)
    )
    respx.get(BA_ALERTS_URL).mock(return_value=httpx.Response(500))
    body = client.get("/api/alerts", params={"agency": "all"}).json()
    assert body["stale"] is True  # the degraded feed is flagged, not fatal
    assert all(alert["agency"] == "ct" for alert in body["alerts"])


@respx.mock
def test_all_alerts_with_both_feeds_down_is_502():
    respx.get(url__startswith=CT_ALERTS_URL).mock(return_value=httpx.Response(500))
    respx.get(BA_ALERTS_URL).mock(return_value=httpx.Response(500))
    response = client.get("/api/alerts", params={"agency": "all"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_unavailable"


def test_health_exposes_bart_caches_and_call_budget():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "bart_upstream_calls_last_hour" in body
    assert {"stop_monitoring", "alerts", "bart_trip_updates", "bart_alerts"} <= set(body["caches"])
