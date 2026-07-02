"""Station registry loaded once from data/stations.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "stations.json"


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    lat: float
    lon: float
    stop_nb: str
    stop_sb: str
    order: int


_raw: dict = json.loads(DATA_PATH.read_text(encoding="utf-8"))
STATIONS: list[Station] = [Station(**s) for s in _raw["stations"]]
_BY_ID: dict[str, Station] = {s.id: s for s in STATIONS}
RAW_PAYLOAD: dict = {"stations": _raw["stations"]}


def get(station_id: str) -> Station | None:
    return _BY_ID.get(station_id)


def direction(origin: Station, destination: Station) -> str:
    """NB = toward San Francisco (order 0)."""
    return "NB" if origin.order > destination.order else "SB"


def platform_codes(origin: Station, destination: Station) -> tuple[str, str, str]:
    """Return (origin_stop_code, destination_stop_code, direction)."""
    if direction(origin, destination) == "NB":
        return origin.stop_nb, destination.stop_nb, "NB"
    return origin.stop_sb, destination.stop_sb, "SB"
