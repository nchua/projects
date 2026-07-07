"""Caltrain Commute Helper — FastAPI app.

API routes first, then the static frontend mount (order matters: the mount
must never shadow /api). All endpoints return times as ISO-8601 with offset;
the frontend renders them in America/Los_Angeles (this server runs UTC).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import bart, bart_pairs, bart_stations, cross, departures, stations, transit511
from app.upstream import UpstreamNeverFetchedError

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader for local dev; Railway injects real env vars.
    (No app module reads env at import time — transit511 reads per request —
    so loading after imports is safe.)"""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

app = FastAPI(title="Caltrain Commute Helper")

DEFAULT_LIMIT = 4
MAX_LIMIT = 10


# Registered on the Starlette base class so routing 404s and StaticFiles
# errors also come back in the spec's {"error": {code, message}} shape.
@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": str(exc.errors()[:3])}},
    )


# endpoint name (the exception's arg) → upstream display name; keeps the 511
# error body byte-identical to the pre-BART app
_UPSTREAM_NAMES = {
    "StopMonitoring": "511.org",
    "servicealerts": "511.org",
    "tripupdate.aspx": "bart.gov",
    "alerts.aspx": "bart.gov",
}


@app.exception_handler(UpstreamNeverFetchedError)
async def _upstream_exception_handler(request: Request, exc: UpstreamNeverFetchedError) -> JSONResponse:
    upstream = _UPSTREAM_NAMES.get(str(exc), "The realtime feed")
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "upstream_unavailable", "message": f"{upstream} is unreachable and no cached data exists yet."}},
    )


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@app.get("/api/health")
async def health() -> dict:
    """Liveness + cache/rate visibility. Never calls upstream."""
    return {
        "status": "ok",
        "upstream_calls_last_hour": transit511.upstream_calls_last_hour(),
        "bart_upstream_calls_last_hour": bart.upstream_calls_last_hour(),
        "caches": {**transit511.cache_status(), **bart.cache_status()},
    }


@app.get("/api/stations")
async def list_stations() -> dict:
    """The bundled station registries. Never calls upstream. The original
    `stations` key is untouched — deployed frontends ignore the new key."""
    return {**stations.RAW_PAYLOAD, "bart_stations": bart_stations.RAW_STATIONS}


async def _caltrain_departures(origin: str, destination: str, limit: int) -> dict:
    """The pre-BART departures path, byte-identical to the original."""
    origin_station = stations.get(origin)
    destination_station = stations.get(destination)
    if origin_station is None or destination_station is None:
        unknown = origin if origin_station is None else destination
        raise _error(400, "unknown_station", f"Unknown station id: {unknown!r}")
    if origin_station.id == destination_station.id:
        raise _error(400, "same_station", "Origin and destination must differ.")

    payload, fetched_at, stale = await transit511.get_stop_monitoring()
    origin_stop, destination_stop, direction = stations.platform_codes(origin_station, destination_station)
    return {
        "agency": "ct",
        "origin": {"id": origin_station.id, "name": origin_station.name, "stop_code": origin_stop},
        "destination": {
            "id": destination_station.id,
            "name": destination_station.name,
            "stop_code": destination_stop,
        },
        "direction": direction,
        "as_of": fetched_at.isoformat(),
        "stale": stale,
        "departures": departures.pair_departures(payload, origin_stop, destination_stop, limit),
    }


async def _bart_departures(origin: str, destination: str, limit: int) -> dict:
    """BART pair departures: direct trips, or transfer itineraries when no
    single train serves the pair (SPEC-BART §7.2). No direction field —
    direction is meaningless on a branching network."""
    origin_station = bart_stations.get(origin)
    destination_station = bart_stations.get(destination)
    if origin_station is None or destination_station is None:
        unknown = origin if origin_station is None else destination
        raise _error(400, "unknown_station", f"Unknown station id: {unknown!r}")
    if origin_station.id == destination_station.id:
        raise _error(400, "same_station", "Origin and destination must differ.")

    payload, fetched_at, stale = await bart.get_trip_updates()
    return {
        "agency": "ba",
        "origin": {
            "id": origin_station.id,
            "abbr": origin_station.abbr,
            "name": origin_station.name,
        },
        "destination": {
            "id": destination_station.id,
            "abbr": destination_station.abbr,
            "name": destination_station.name,
        },
        "as_of": fetched_at.isoformat(),
        "stale": stale,
        "departures": bart_pairs.pair_departures(payload, origin_station, destination_station, limit),
    }


def _parse_cross_end(value: str) -> tuple[str, stations.Station | bart_stations.Station]:
    """'ct:san_carlos' → ('ct', Station) — the frontend's option-value format
    (SPEC-V2 §7.2)."""
    agency, _, ident = value.partition(":")
    if agency == "ct":
        station = stations.get(ident)
    elif agency == "ba":
        station = bart_stations.get(ident)
    else:
        raise _error(
            400, "unknown_agency",
            f"Cross-agency endpoints must be 'ct:<id>' or 'ba:<id>', got {value!r}.",
        )
    if station is None:
        raise _error(400, "unknown_station", f"Unknown station id: {ident!r}")
    return agency, station


async def _cross_departures(origin: str, destination: str, limit: int) -> dict:
    """Caltrain↔BART itineraries connecting at Millbrae (SPEC-V2 §7)."""
    origin_agency, origin_station = _parse_cross_end(origin)
    destination_agency, destination_station = _parse_cross_end(destination)
    if origin_agency == destination_agency:
        raise _error(
            400, "unknown_agency",
            "Cross-agency pairs need one Caltrain and one BART station.",
        )
    if cross.CT_MILLBRAE_ID in (origin_station.id, destination_station.id):
        raise _error(
            400, "degenerate_pair",
            "Board at Millbrae directly — add a single-agency pair instead.",
        )

    (sm_payload, sm_fetched, sm_stale), (ba_feed, ba_fetched, ba_stale) = await asyncio.gather(
        transit511.get_stop_monitoring(), bart.get_trip_updates()
    )
    ct_first = origin_agency == "ct"
    ct_station = origin_station if ct_first else destination_station
    ba_station = destination_station if ct_first else origin_station

    def _end(agency: str, station: stations.Station | bart_stations.Station) -> dict:
        if agency == "ct":
            return {"agency": "ct", "id": station.id, "name": station.name}
        return {"agency": "ba", "id": station.id, "abbr": station.abbr, "name": station.name}

    itineraries, empty_reason = cross.pair_itineraries(
        sm_payload, ba_feed, ct_station, ba_station, ct_first, limit
    )
    response = {
        "agency": "xa",
        "origin": _end(origin_agency, origin_station),
        "destination": _end(destination_agency, destination_station),
        "as_of": min(sm_fetched, ba_fetched).isoformat(),
        "stale": sm_stale or ba_stale,
        "departures": itineraries,
    }
    if empty_reason:  # additive, only on empty xa boards (SPEC-V2 §13-3)
        response["empty_reason"] = empty_reason
    return response


@app.get("/api/departures")
async def get_departures(
    origin: str,
    destination: str,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    agency: str = "ct",
) -> dict:
    """Upcoming departures for a station pair, joined to arrival times."""
    if agency == "ct":
        return await _caltrain_departures(origin, destination, limit)
    if agency == "ba":
        return await _bart_departures(origin, destination, limit)
    if agency == "xa":
        return await _cross_departures(origin, destination, limit)
    raise _error(400, "unknown_agency", f"Unknown agency: {agency!r} (expected 'ct', 'ba', or 'xa').")


async def _caltrain_alerts() -> dict:
    payload, fetched_at, stale = await transit511.get_service_alerts()
    return {
        "agency": "ct",
        "as_of": fetched_at.isoformat(),
        "stale": stale,
        "alerts": departures.parse_alerts(payload),
    }


async def _bart_alerts() -> dict:
    payload, fetched_at, stale = await bart.get_alerts()
    # elevator advisories are best-effort (SPEC-V2 §6.2): key-gated, and NO
    # failure of the legacy bsa endpoint — unreachable, malformed, or an
    # unexpected shape — may ever degrade the GTFS-RT alerts
    try:
        advisories, _, _ = await bart.get_elevator_advisories()
    except Exception:  # noqa: BLE001
        advisories = []
    return {
        "agency": "ba",
        "as_of": fetched_at.isoformat(),
        "stale": stale,
        "alerts": bart_pairs.parse_alerts(payload) + advisories,
    }


@app.get("/api/alerts")
async def get_alerts(agency: str = "ct") -> dict:
    """Currently-active system alerts, flattened from GTFS-RT.

    agency=all merges both feeds; one feed being down never hides the other's
    alerts (the stale flag covers the degraded one).
    """
    if agency == "ct":
        return await _caltrain_alerts()
    if agency == "ba":
        return await _bart_alerts()
    if agency != "all":
        raise _error(400, "unknown_agency", f"Unknown agency: {agency!r} (expected 'ct', 'ba', or 'all').")

    results = []
    for result in await asyncio.gather(_caltrain_alerts(), _bart_alerts(), return_exceptions=True):
        if isinstance(result, UpstreamNeverFetchedError):
            results.append(None)  # one feed down never hides the other's alerts
        elif isinstance(result, BaseException):
            raise result
        else:
            results.append(result)
    if all(result is None for result in results):
        raise UpstreamNeverFetchedError("alerts")
    fetched = [result for result in results if result is not None]
    return {
        "agency": "all",
        "as_of": min(result["as_of"] for result in fetched),
        "stale": any(result["stale"] for result in fetched) or len(fetched) < 2,
        "alerts": [
            {**alert, "agency": result["agency"]} for result in fetched for alert in result["alerts"]
        ],
    }


# Static frontend — registered last so it never shadows /api routes.
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
