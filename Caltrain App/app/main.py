"""Caltrain Commute Helper — FastAPI app.

API routes first, then the static frontend mount (order matters: the mount
must never shadow /api). All endpoints return times as ISO-8601 with offset;
the frontend renders them in America/Los_Angeles (this server runs UTC).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import departures, stations, transit511

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


@app.exception_handler(transit511.UpstreamNeverFetchedError)
async def _upstream_exception_handler(request: Request, exc: transit511.UpstreamNeverFetchedError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "upstream_unavailable", "message": "511.org is unreachable and no cached data exists yet."}},
    )


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@app.get("/api/health")
async def health() -> dict:
    """Liveness + cache/rate visibility. Never calls upstream."""
    return {
        "status": "ok",
        "upstream_calls_last_hour": transit511.upstream_calls_last_hour(),
        "caches": transit511.cache_status(),
    }


@app.get("/api/stations")
async def list_stations() -> dict:
    """The bundled station registry. Never calls upstream."""
    return stations.RAW_PAYLOAD


@app.get("/api/departures")
async def get_departures(
    origin: str,
    destination: str,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict:
    """Upcoming departures for a station pair, joined to arrival times."""
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


@app.get("/api/alerts")
async def get_alerts() -> dict:
    """Currently-active system alerts, flattened from GTFS-RT."""
    payload, fetched_at, stale = await transit511.get_service_alerts()
    return {
        "as_of": fetched_at.isoformat(),
        "stale": stale,
        "alerts": departures.parse_alerts(payload),
    }


# Static frontend — registered last so it never shadows /api routes.
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
