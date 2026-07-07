"""BART elevator advisories (SPEC-V2 §6): prose parsing on the real capture,
key gating, and the best-effort merge into /api/alerts."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from app import bart
from app.main import app
from conftest import FIXTURES
from fastapi.testclient import TestClient

client = TestClient(app)

ELEV_FIXTURE = json.loads((FIXTURES / "bart" / "elev.json").read_text(encoding="utf-8"))
BA_ALERTS_URL = f"{bart.BASE_URL}/alerts.aspx"
ELEV_URL = bart.ELEV_URL


def alert_feed_bytes() -> bytes:
    return (FIXTURES / "bart" / "alerts.pb").read_bytes()


# --- prose parsing -------------------------------------------------------------


def test_real_capture_parses_mlbr_and_rich_outage():
    [advisory] = bart.parse_elevator_advisories(ELEV_FIXTURE)
    assert advisory["stops"] == ["MLBR", "RICH"]
    assert advisory["id"] == "elev:MLBR,RICH"  # set-stable, not the feed's time-derived @id
    assert advisory["type"] == "elevator"
    assert advisory["header"] == "Elevator out of service at Millbrae, Richmond"
    assert "2 elevators out of service" in advisory["description"]
    assert advisory["active_period"] == {"start": None, "end": None}


def _payload(description: str) -> dict:
    return {"root": {"bsa": [{"@id": "x", "station": "BART", "type": "ELEVATOR",
                              "description": {"#cdata-section": description}}]}}


def test_zero_outage_message_produces_no_advisories():
    payload = _payload("Attention passengers: All elevators are in service. Thank you.")
    assert bart.parse_elevator_advisories(payload) == []


def test_singleton_bsa_object_parses():
    # XML→JSON collapses one-element arrays to bare objects, like 511
    payload = _payload("There is 1 elevator out of service at this time: EMBR: Street")
    payload["root"]["bsa"] = payload["root"]["bsa"][0]
    [advisory] = bart.parse_elevator_advisories(payload)
    assert advisory["stops"] == ["EMBR"]


def test_unresolvable_prose_degrades_to_unscoped_alert():
    text = "There is 1 elevator out of service at this time: XQZV: Mystery"
    [advisory] = bart.parse_elevator_advisories(_payload(text))
    assert advisory["stops"] == []
    assert advisory["id"] == "elev:unscoped"
    assert advisory["header"] == text  # never dropped (§6.2)


# --- key gating + merge ----------------------------------------------------------


@pytest.fixture
def bart_key(monkeypatch):
    monkeypatch.setenv("BART_API_KEY", "TEST-KEY-0000")


@pytest.fixture
def no_bart_key(monkeypatch):
    monkeypatch.delenv("BART_API_KEY", raising=False)


@respx.mock
@pytest.mark.anyio
async def test_no_key_means_no_fetch(no_bart_key):
    route = respx.get(url__startswith=ELEV_URL)
    advisories, fetched_at, stale = await bart.get_elevator_advisories()
    assert (advisories, fetched_at, stale) == ([], None, False)
    assert not route.called
    assert bart.upstream_calls_last_hour() == 0


@respx.mock
def test_alerts_endpoint_merges_elevator_advisories(bart_key):
    respx.get(BA_ALERTS_URL).mock(return_value=httpx.Response(200, content=alert_feed_bytes()))
    respx.get(url__startswith=ELEV_URL).mock(
        return_value=httpx.Response(200, json=ELEV_FIXTURE)
    )
    body = client.get("/api/alerts?agency=ba").json()
    elevator = [a for a in body["alerts"] if a.get("type") == "elevator"]
    assert len(elevator) == 1
    assert elevator[0]["stops"] == ["MLBR", "RICH"]
    # the GTFS-RT alerts are still there alongside
    assert len(body["alerts"]) > 1


@respx.mock
def test_elevator_failure_never_degrades_gtfsrt_alerts(bart_key):
    respx.get(BA_ALERTS_URL).mock(return_value=httpx.Response(200, content=alert_feed_bytes()))
    respx.get(url__startswith=ELEV_URL).mock(return_value=httpx.Response(500))
    body = client.get("/api/alerts?agency=ba").json()
    assert body["stale"] is False
    assert body["alerts"]  # GTFS-RT alerts intact, advisories simply absent
    assert not any(a.get("type") == "elevator" for a in body["alerts"])


@respx.mock
def test_health_exposes_elev_cache_entry():
    body = client.get("/api/health").json()
    assert body["caches"]["bart_elev"] == {"age_seconds": None, "have_data": False}
