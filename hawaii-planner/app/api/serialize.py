"""ORM -> JSON serializers, including the timeline merge for day payloads."""
from datetime import time as time_type

from sqlalchemy.orm import Session, joinedload

from app.models.day import ScheduleItem, TripDay
from app.models.idea import VOTE_SCORES, Idea, Vote
from app.models.member import Member
from app.models.region import DriveTime, Region
from app.services.timeline import (
    HOME_REGION_ID,
    TimelineStop,
    compute_timeline,
    fmt_min,
)

FREE_TEXT_DEFAULT_DURATION_MIN = 90
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def csv_list(value: str | None) -> list[str]:
    return [token for token in (value or "").split(",") if token]


def _to_minutes(t: time_type) -> int:
    return t.hour * 60 + t.minute


def _time_str(t: time_type | None) -> str | None:
    return None if t is None else f"{t.hour:02d}:{t.minute:02d}"


def build_drive_lookup(db: Session):
    """Load the matrix once; return (lookup_fn, rows_json)."""
    rows = db.query(DriveTime).all()
    table = {
        (row.region_a, row.region_b): (row.minutes, csv_list(row.flags))
        for row in rows
    }

    def lookup(a: str, b: str) -> tuple[int, list[str]]:
        pair = (a, b) if a <= b else (b, a)
        entry = table.get(pair)
        if entry is None:  # unseeded pair — degrade gracefully, don't 500
            return (10, []) if a == b else (30, [])
        return entry

    rows_json = [
        {
            "region_a": row.region_a,
            "region_b": row.region_b,
            "minutes": row.minutes,
            "flags": csv_list(row.flags),
        }
        for row in rows
    ]
    return lookup, rows_json


def member_out(member: Member) -> dict:
    return {"id": member.id, "name": member.name, "color": member.color}


def region_out(region: Region) -> dict:
    return {
        "id": region.id,
        "name": region.name,
        "sort_order": region.sort_order,
        "tour_order": region.tour_order,
    }


def idea_score(votes: list[Vote]) -> int:
    return sum(VOTE_SCORES.get(vote.value, 0) for vote in votes)


def idea_out(idea: Idea, scheduled_day_ids: list[str]) -> dict:
    return {
        "id": idea.id,
        "title": idea.title,
        "kind": idea.kind,
        "region_id": idea.region_id,
        "duration_min": idea.duration_min,
        "yelp_url": idea.yelp_url,
        "maps_url": idea.maps_url,
        "notes": idea.notes,
        "recommended_by": idea.recommended_by,
        "reservation_rule": idea.reservation_rule,
        "closed_days": csv_list(idea.closed_days),
        "difficulty": idea.difficulty,
        "best_time": idea.best_time,
        "meal_tags": csv_list(idea.meal_tags),
        "created_by_member_id": idea.created_by_member_id,
        # Stored naive-UTC; mark it so JS Date.parse doesn't read it as local.
        "created_at": idea.created_at.isoformat() + "Z" if idea.created_at else None,
        "score": idea_score(idea.votes),
        "votes": [
            {"member_id": vote.member_id, "value": vote.value} for vote in idea.votes
        ],
        "scheduled_day_ids": scheduled_day_ids,
    }


def _item_idea(item: ScheduleItem) -> Idea | None:
    """The pool idea behind a stop, or None for a free-text stop."""
    return item.idea if item.idea_id is not None else None


def _duration_min(item: ScheduleItem, idea: Idea | None) -> int:
    """Override wins; otherwise the idea's own duration, else the free-text default."""
    return item.duration_override_min or (
        idea.duration_min if idea else FREE_TEXT_DEFAULT_DURATION_MIN
    )


def _stop_from_item(item: ScheduleItem) -> TimelineStop:
    idea = _item_idea(item)
    return TimelineStop(
        id=item.id,
        title=idea.title if idea else (item.free_text_title or ""),
        region_id=idea.region_id if idea else item.free_text_region_id,
        duration_min=_duration_min(item, idea),
        fixed_start_min=(
            None if item.fixed_start_time is None else _to_minutes(item.fixed_start_time)
        ),
        drive_override_min=item.drive_override_min,
        closed_days=frozenset(csv_list(idea.closed_days)) if idea else frozenset(),
    )


def day_out(day: TripDay, drive_lookup) -> dict:
    """Serialize a day with its computed timeline merged into each item."""
    items = sorted(day.items, key=lambda i: i.position)
    weekday = WEEKDAYS[day.date.weekday()] if day.date else None
    computed = compute_timeline(
        start_min=_to_minutes(day.start_time),
        end_min=_to_minutes(day.end_time),
        weekday=weekday,
        stops=[_stop_from_item(item) for item in items],
        drive_lookup=drive_lookup,
    )

    items_json = []
    for item, calc in zip(items, computed["items"]):
        idea = _item_idea(item)
        items_json.append(
            {
                "id": item.id,
                "idea_id": item.idea_id,
                "title": idea.title if idea else item.free_text_title,
                "kind": idea.kind if idea else None,
                "region_id": calc["region_id"],
                "yelp_url": idea.yelp_url if idea else None,
                "maps_url": idea.maps_url if idea else None,
                "reservation_rule": idea.reservation_rule if idea else None,
                "difficulty": idea.difficulty if idea else None,
                "best_time": idea.best_time if idea else None,
                "notes": item.notes,
                "position": item.position,
                "duration_min": _duration_min(item, idea),
                "duration_override_min": item.duration_override_min,
                "fixed_start_time": _time_str(item.fixed_start_time),
                "drive_override_min": item.drive_override_min,
                "drive_minutes": calc["drive_minutes"],
                "drive_flags": calc["drive_flags"],
                "start": fmt_min(calc["start_min"]),
                "end": fmt_min(calc["end_min"]),
                "start_min": calc["start_min"],
                "end_min": calc["end_min"],
                "leave_by": (
                    None
                    if calc["leave_by_min"] is None
                    else fmt_min(calc["leave_by_min"])
                ),
                "free_gap_min": calc["free_gap_min"],
                "warnings": calc["warnings"],
            }
        )

    return_leg = computed["return_leg"]
    if return_leg is not None:
        return_leg = {
            **return_leg,
            "arrive_hotel": fmt_min(return_leg["arrive_hotel_min"]),
        }

    return {
        "id": day.id,
        "date": day.date.isoformat() if day.date else None,
        "label": day.label,
        "start_time": _time_str(day.start_time),
        "end_time": _time_str(day.end_time),
        "notes": day.notes,
        "sort_order": day.sort_order,
        "items": items_json,
        "return_leg": return_leg,
        "total_drive_minutes": computed["total_drive_minutes"],
        "day_ends_at": fmt_min(computed["day_ends_at_min"]),
        "warnings": computed["warnings"],
        "home_region_id": HOME_REGION_ID,
    }


def load_day(db: Session, day_id: str) -> TripDay | None:
    return (
        db.query(TripDay)
        .options(joinedload(TripDay.items).joinedload(ScheduleItem.idea))
        .filter(TripDay.id == day_id)
        .first()
    )


def scheduled_day_ids_by_idea(db: Session) -> dict[str, list[str]]:
    rows = (
        db.query(ScheduleItem.idea_id, ScheduleItem.trip_day_id)
        .filter(ScheduleItem.idea_id.isnot(None))
        .all()
    )
    mapping: dict[str, list[str]] = {}
    for idea_id, day_id in rows:
        day_ids = mapping.setdefault(idea_id, [])
        if day_id not in day_ids:
            day_ids.append(day_id)
    return mapping
