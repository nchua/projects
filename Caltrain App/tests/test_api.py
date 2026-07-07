"""Endpoint tests via TestClient with the upstream mocked by respx."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import respx
from app import transit511
from app.main import app
from conftest import bom_bytes as _bom
from conftest import make_visit, payload_of
from fastapi.testclient import TestClient

client = TestClient(app)

SM_URL = f"{transit511.BASE_URL}/StopMonitoring"
ALERTS_URL = f"{transit511.BASE_URL}/servicealerts"


def _fresh_sm_payload() -> dict:
    now = datetime.now(timezone.utc)

    def ts(minutes: int) -> str:
        return (now + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return payload_of(
        make_visit("117", "70131", aimed_dep=ts(9), expected_dep=ts(14), line="Limited"),
        make_visit("117", "70011", aimed_arr=ts(52), expected_arr=ts(57), line="Limited"),
    )


@respx.mock
def test_health_never_calls_upstream():
    # No respx routes registered: any upstream call would raise.
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["upstream_calls_last_hour"] == 0
    assert body["caches"]["stop_monitoring"]["have_data"] is False


@respx.mock
def test_stations_served_from_bundle():
    response = client.get("/api/stations")
    assert response.status_code == 200
    stations = response.json()["stations"]
    assert len(stations) == 30
    san_carlos = next(s for s in stations if s["id"] == "san_carlos")
    assert san_carlos["stop_nb"] == "70131"
    assert san_carlos["stop_sb"] == "70132"


@respx.mock
def test_unknown_station_is_400():
    response = client.get("/api/departures", params={"origin": "narnia", "destination": "san_francisco"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_station"


@respx.mock
def test_same_station_is_400():
    response = client.get("/api/departures", params={"origin": "san_carlos", "destination": "san_carlos"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "same_station"


@respx.mock
def test_departures_happy_path_northbound():
    respx.get(url__startswith=SM_URL).mock(
        return_value=httpx.Response(200, content=_bom(_fresh_sm_payload()))
    )
    response = client.get("/api/departures", params={"origin": "san_carlos", "destination": "san_francisco"})
    assert response.status_code == 200
    body = response.json()
    assert body["direction"] == "NB"
    assert body["origin"]["stop_code"] == "70131"
    assert body["destination"]["stop_code"] == "70011"
    assert body["stale"] is False
    assert len(body["departures"]) == 1
    row = body["departures"][0]
    assert row["train"] == "117"
    assert row["train_type"] == "Limited"
    assert row["status"] == "late"
    assert row["delay_seconds"] == 300
    assert row["arrival"]["expected"] is not None


@respx.mock
def test_departures_upstream_down_cold_cache_is_502():
    respx.get(url__startswith=SM_URL).mock(return_value=httpx.Response(500, content=b"down"))
    response = client.get("/api/departures", params={"origin": "san_carlos", "destination": "san_francisco"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_unavailable"


@respx.mock
def test_departures_upstream_down_serves_stale(monkeypatch):
    monkeypatch.setattr(transit511, "STOP_MONITORING_TTL_S", 0)
    route = respx.get(url__startswith=SM_URL)
    route.side_effect = [
        httpx.Response(200, content=_bom(_fresh_sm_payload())),
        httpx.Response(500, content=b"down"),
    ]
    first = client.get("/api/departures", params={"origin": "san_carlos", "destination": "san_francisco"})
    second = client.get("/api/departures", params={"origin": "san_carlos", "destination": "san_francisco"})
    assert first.json()["stale"] is False
    assert second.status_code == 200
    assert second.json()["stale"] is True
    assert second.json()["departures"] == first.json()["departures"]


@respx.mock
def test_alerts_endpoint_flattens_active_alerts():
    now = datetime.now(timezone.utc)
    payload = {
        "Entities": [
            {
                "Id": "a1",
                "Alert": {
                    "ActivePeriods": [
                        {
                            "Start": int((now - timedelta(hours=2)).timestamp()),
                            "End": int((now + timedelta(days=2)).timestamp()),
                        }
                    ],
                    "HeaderText": {"Translations": [{"Text": "Elevator out", "Language": "en"}]},
                    "DescriptionText": {"Translations": [{"Text": "Use the ramp", "Language": "en"}]},
                },
            }
        ]
    }
    respx.get(url__startswith=ALERTS_URL).mock(return_value=httpx.Response(200, content=_bom(payload)))
    response = client.get("/api/alerts")
    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is False
    assert body["alerts"] == [
        {
            "id": "a1",
            "header": "Elevator out",
            "description": "Use the ramp",
            "active_period": body["alerts"][0]["active_period"],
            "stops": [],
            "type": "elevator",  # tagged by header/description text (SPEC-V2 §6.1)
        }
    ]


@respx.mock
def test_frontend_served_at_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@respx.mock
def test_validation_errors_use_spec_error_shape():
    response = client.get("/api/departures", params={"origin": "san_carlos"})  # missing destination
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"

    response = client.get(
        "/api/departures",
        params={"origin": "san_carlos", "destination": "san_francisco", "limit": "0"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


@respx.mock
def test_unknown_api_path_uses_spec_error_shape():
    response = client.get("/api/nonexistent")
    assert response.status_code == 404
    assert "error" in response.json()
