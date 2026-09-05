"""
Daily activity series (ARISE v3 spec §8.2 athlete context / §6.5 Condition v2).

Flattens ``daily_activity`` — which is unique per (user, date, source) — into
one row per calendar day so the coach context builder and the HRV-trend
input can consume a fixed-shape series without knowing about sources.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.activity import DailyActivity

# Fixed key order for every row (missing days are present with nulls).
SERIES_KEYS = (
    "local_date",
    "sleep_hours",
    "hrv",
    "resting_heart_rate",
    "recovery_score",
    "steps",
    "strain",
    "source",
)

# Fields where a WHOOP row wins whenever it has a value; the rest take the
# first non-null value in source-priority order (WHOOP first, then others).
_WHOOP_PREFERRED = ("sleep_hours", "recovery_score", "strain")
_MERGED_FIELDS = ("sleep_hours", "hrv", "resting_heart_rate", "recovery_score", "steps", "strain")


def _is_whoop(source: Optional[str]) -> bool:
    return "whoop" in (source or "").lower()


def _round1(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 1)


def _merge_day(rows: List[DailyActivity]) -> Dict[str, Any]:
    """Merge every source's row for one day into a single dict."""
    ordered = sorted(rows, key=lambda r: (0 if _is_whoop(r.source) else 1, r.source or ""))
    merged: Dict[str, Any] = {key: None for key in _MERGED_FIELDS}
    sources: List[str] = []
    for row in ordered:
        if row.source and row.source not in sources:
            sources.append(row.source)
        for field in _MERGED_FIELDS:
            value = getattr(row, field)
            if value is None:
                continue
            if merged[field] is None:
                merged[field] = value
            elif field in _WHOOP_PREFERRED and _is_whoop(row.source):
                merged[field] = value
    merged["source"] = ",".join(sources) if sources else None
    return merged


def daily_activity_series(
    db: Session, user_id: str, days: int, *, as_of: Optional[date] = None
) -> List[Dict[str, Any]]:
    """One row per calendar day for the last ``days`` days, oldest first.

    Each row carries ``SERIES_KEYS`` in that order; numeric values are rounded
    to one decimal and days with no ``daily_activity`` row are present with
    nulls. Multiple sources on one day are merged per field: WHOOP wins for
    sleep / recovery / strain, HRV and RHR take whichever source has a value
    (WHOOP first). ``source`` lists the contributing sources, comma-joined.
    """
    if days <= 0:
        return []
    # The user's local day comes from the client (spec §12 0a item 1); the
    # server-local day is only a fallback for callers that have none.
    end = as_of or date.today()
    start = end - timedelta(days=days - 1)

    rows = (
        db.query(DailyActivity)
        .filter(
            DailyActivity.user_id == user_id,
            DailyActivity.date >= start,
            DailyActivity.date <= end,
        )
        .all()
    )
    by_day: Dict[date, List[DailyActivity]] = {}
    for row in rows:
        by_day.setdefault(row.date, []).append(row)

    series: List[Dict[str, Any]] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        merged = _merge_day(by_day.get(day, []))
        series.append({
            "local_date": day.isoformat(),
            "sleep_hours": _round1(merged.get("sleep_hours")),
            "hrv": _round1(merged.get("hrv")),
            "resting_heart_rate": _round1(merged.get("resting_heart_rate")),
            "recovery_score": _round1(merged.get("recovery_score")),
            "steps": _round1(merged.get("steps")),
            "strain": _round1(merged.get("strain")),
            "source": merged.get("source"),
        })
    return series


__all__ = ["SERIES_KEYS", "daily_activity_series"]
