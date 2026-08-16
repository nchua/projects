"""Day-timeline computation.

Pure functions, no DB access: given a day window, an ordered list of stops,
and a drive-time lookup, produce arrival/departure times, drive legs, the
return-to-hotel leg, and warnings. Computed on every read — never persisted —
so reorders/edits can never leave stale times behind.

All times are minutes since midnight, Hawaii wall-clock. A day that spills
past midnight keeps counting up (e.g. 22:30 -> 1350); formatting wraps.
"""
from dataclasses import dataclass, field
from typing import Callable

HOME_REGION_ID = "WAI"
# Parking, bathrooms, loading five people into one car — applied to every leg.
TRANSITION_BUFFER_MIN = 10

WEEKDAY_TOKENS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# drive_lookup(region_a, region_b) -> (typical minutes, caution flags)
DriveLookup = Callable[[str, str], tuple[int, list[str]]]


@dataclass
class TimelineStop:
    """Input row for the computation — an adapter builds these from ORM objects."""

    id: str
    title: str
    region_id: str | None  # None (free-text stop) = stay in previous region
    duration_min: int
    fixed_start_min: int | None = None
    drive_override_min: int | None = None
    closed_days: frozenset = field(default_factory=frozenset)


def fmt_min(minutes: int) -> str:
    """Minutes since midnight -> \"HH:MM\" (24h, wrapping past midnight)."""
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _leg(
    from_region: str,
    to_region: str,
    drive_override_min: int | None,
    drive_lookup: DriveLookup,
) -> tuple[int, list[str]]:
    """Total inbound leg cost (matrix + buffer, or the override verbatim)."""
    if drive_override_min is not None:
        return drive_override_min, []
    minutes, flags = drive_lookup(from_region, to_region)
    return minutes + TRANSITION_BUFFER_MIN, flags


def compute_timeline(
    *,
    start_min: int,
    end_min: int,
    weekday: str | None,
    stops: list[TimelineStop],
    drive_lookup: DriveLookup,
) -> dict:
    """Compute the day's schedule.

    Returns {"items": [...], "return_leg": {...} | None,
             "total_drive_minutes": int, "day_ends_at_min": int,
             "warnings": [...]}.
    """
    items: list[dict] = []
    day_warnings: list[dict] = []
    cursor = start_min
    prev_region = HOME_REGION_ID
    total_drive = 0

    for stop in stops:
        region = stop.region_id or prev_region
        drive, flags = _leg(prev_region, region, stop.drive_override_min, drive_lookup)
        total_drive += drive
        warnings: list[dict] = []
        leave_by: int | None = None
        free_gap: int | None = None

        if stop.fixed_start_min is not None:
            start = stop.fixed_start_min
            leave_by = start - drive
            if cursor > leave_by:
                warnings.append(
                    {
                        "code": "infeasible_arrival",
                        "late_minutes": cursor - leave_by,
                        "message": f"Arriving ~{cursor - leave_by} min late to {stop.title}",
                    }
                )
            else:
                gap = start - (cursor + drive)
                if gap > 0:
                    free_gap = gap
        else:
            start = cursor + drive

        if weekday is not None and weekday in stop.closed_days:
            warnings.append(
                {
                    "code": "closed_on_day",
                    "message": f"{stop.title} is closed on {weekday.capitalize()}",
                }
            )

        end = start + stop.duration_min
        items.append(
            {
                "stop_id": stop.id,
                "region_id": region,
                "drive_minutes": drive,
                "drive_flags": flags,
                "depart_prev_min": start - drive,
                "start_min": start,
                "end_min": end,
                "leave_by_min": leave_by,
                "free_gap_min": free_gap,
                "warnings": warnings,
            }
        )
        cursor = end
        prev_region = region

    return_leg: dict | None = None
    day_ends_at = cursor
    if stops:
        drive, flags = _leg(prev_region, HOME_REGION_ID, None, drive_lookup)
        total_drive += drive
        arrive_hotel = cursor + drive
        day_ends_at = arrive_hotel
        return_leg = {
            "from_region_id": prev_region,
            "drive_minutes": drive,
            "drive_flags": flags,
            "arrive_hotel_min": arrive_hotel,
        }
        if arrive_hotel > end_min:
            day_warnings.append(
                {
                    "code": "overpacked",
                    "message": f"Overpacked — back at hotel {fmt_min(arrive_hotel)}",
                }
            )

    return {
        "items": items,
        "return_leg": return_leg,
        "total_drive_minutes": total_drive,
        "day_ends_at_min": day_ends_at,
        "warnings": day_warnings,
    }
