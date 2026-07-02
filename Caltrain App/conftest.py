"""Root conftest: makes `app` importable, resets client state per test, and
hosts the shared 511-payload builders used across test files."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("TRANSIT_511_API_KEY", "test-key")

FIXTURES = Path(__file__).parent / "tests" / "fixtures"


def bom_bytes(payload: dict) -> bytes:
    """Encode a payload the way 511 serves it: UTF-8 with a leading BOM."""
    return b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")


def make_visit(
    train: str,
    stop: str,
    aimed_dep: str | None = None,
    expected_dep: str | None = None,
    aimed_arr: str | None = None,
    expected_arr: str | None = None,
    line: str = "Local Weekday",
    destination_ref: str | None = None,
    service_date: str = "2026-07-01",
) -> dict:
    """One MonitoredStopVisit in 511's StopMonitoring shape."""
    call: dict = {"StopPointRef": stop}
    if aimed_dep:
        call["AimedDepartureTime"] = aimed_dep
    if expected_dep:
        call["ExpectedDepartureTime"] = expected_dep
    if aimed_arr:
        call["AimedArrivalTime"] = aimed_arr
    if expected_arr:
        call["ExpectedArrivalTime"] = expected_arr
    journey: dict = {
        "LineRef": line,
        "FramedVehicleJourneyRef": {"DataFrameRef": service_date, "DatedVehicleJourneyRef": train},
        "MonitoredCall": call,
    }
    if destination_ref:
        journey["DestinationRef"] = destination_ref
    return {"MonitoringRef": stop, "MonitoredVehicleJourney": journey}


def payload_of(*visits: dict, siri_wrapper: bool = False, collapse_single: bool = False) -> dict:
    """A StopMonitoring payload; can mimic 511's structural quirks."""
    monitored: object = list(visits)
    if collapse_single and len(visits) == 1:
        monitored = visits[0]  # 511 collapses 1-element arrays to bare objects
    sd = {"StopMonitoringDelivery": {"MonitoredStopVisit": monitored}}
    return {"Siri": {"ServiceDelivery": sd}} if siri_wrapper else {"ServiceDelivery": sd}


@pytest.fixture(autouse=True)
def _reset_transit511():
    from app import transit511

    transit511.reset()
    yield
    transit511.reset()


@pytest.fixture
def stopmonitoring_bytes() -> bytes:
    """Real captured 511 response, raw bytes, UTF-8 BOM intact."""
    return (FIXTURES / "stopmonitoring_all.json").read_bytes()


@pytest.fixture
def servicealerts_bytes() -> bytes:
    return (FIXTURES / "servicealerts.json").read_bytes()


@pytest.fixture
def stopmonitoring_payload(stopmonitoring_bytes) -> dict:
    return json.loads(stopmonitoring_bytes.decode("utf-8-sig"))


@pytest.fixture
def servicealerts_payload(servicealerts_bytes) -> dict:
    return json.loads(servicealerts_bytes.decode("utf-8-sig"))
