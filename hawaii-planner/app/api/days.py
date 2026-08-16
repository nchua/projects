"""Trip days and schedule items — every mutation returns the recomputed day."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serialize import build_drive_lookup, day_out, idea_score, load_day
from app.core.database import get_db
from app.core.versioning import bump_version
from app.models.day import ScheduleItem, TripDay
from app.models.idea import Idea
from app.models.region import Region
from app.schemas.day import BulkAddIn, DayCreate, DayPatch, ItemCreate, ItemPatch, OrderIn

router = APIRouter()


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def _get_day(db: Session, day_id: str) -> TripDay:
    day = load_day(db, day_id)
    if day is None:
        raise _not_found("day_not_found", "That day no longer exists.")
    return day


def _day_response(db: Session, day_id: str, version: int) -> dict:
    drive_lookup, _ = build_drive_lookup(db)
    day = load_day(db, day_id)
    return {"version": version, "day": day_out(day, drive_lookup) if day else None}


def _next_position(day: TripDay) -> int:
    return max((item.position for item in day.items), default=-1) + 1


@router.post("/api/days")
def create_day(body: DayCreate, db: Session = Depends(get_db)) -> dict:
    max_sort = db.query(TripDay).count()
    day = TripDay(date=body.date, label=body.label, sort_order=max_sort)
    db.add(day)
    version = bump_version(db)
    db.commit()
    return _day_response(db, day.id, version)


@router.patch("/api/days/{day_id}")
def patch_day(day_id: str, body: DayPatch, db: Session = Depends(get_db)) -> dict:
    day = _get_day(db, day_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(day, field, value)
    version = bump_version(db)
    db.commit()
    return _day_response(db, day_id, version)


@router.delete("/api/days/{day_id}")
def delete_day(day_id: str, db: Session = Depends(get_db)) -> dict:
    day = _get_day(db, day_id)
    db.delete(day)
    version = bump_version(db)
    db.commit()
    return {"version": version, "deleted": day_id}


@router.post("/api/days/{day_id}/items")
def add_item(day_id: str, body: ItemCreate, db: Session = Depends(get_db)) -> dict:
    day = _get_day(db, day_id)
    if body.idea_id is not None and db.get(Idea, body.idea_id) is None:
        raise _not_found("idea_not_found", "That idea no longer exists.")
    if body.free_text_region_id and db.get(Region, body.free_text_region_id) is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_region", "message": "Unknown region."},
        )

    item = ScheduleItem(
        trip_day_id=day.id,
        idea_id=body.idea_id,
        free_text_title=body.free_text_title,
        free_text_region_id=body.free_text_region_id,
        position=body.position if body.position is not None else _next_position(day),
        duration_override_min=body.duration_override_min,
        fixed_start_time=body.fixed_start_time,
        drive_override_min=body.drive_override_min,
        notes=body.notes,
    )
    db.add(item)
    version = bump_version(db)
    db.commit()
    return _day_response(db, day_id, version)


@router.patch("/api/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch, db: Session = Depends(get_db)) -> dict:
    item = db.get(ScheduleItem, item_id)
    if item is None:
        raise _not_found("item_not_found", "That stop no longer exists.")

    updates = body.model_dump(exclude_unset=True)
    if "trip_day_id" in updates:
        target_id = updates.pop("trip_day_id")
        target = _get_day(db, target_id)
        item.trip_day_id = target.id
        item.position = _next_position(target)
    for field, value in updates.items():
        setattr(item, field, value)
    version = bump_version(db)
    db.commit()
    return _day_response(db, item.trip_day_id, version)


@router.delete("/api/items/{item_id}")
def delete_item(item_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(ScheduleItem, item_id)
    if item is None:
        raise _not_found("item_not_found", "That stop no longer exists.")
    day_id = item.trip_day_id
    db.delete(item)
    version = bump_version(db)
    db.commit()
    return _day_response(db, day_id, version)


@router.put("/api/days/{day_id}/order")
def reorder_items(day_id: str, body: OrderIn, db: Session = Depends(get_db)) -> dict:
    """Atomic full-order rewrite — concurrent reorders converge to one complete
    ordering instead of interleaving."""
    day = _get_day(db, day_id)
    current_ids = {item.id for item in day.items}
    if set(body.item_ids) != current_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "stale_order",
                "message": "The day changed under you — refresh and try again.",
            },
        )
    by_id = {item.id: item for item in day.items}
    for position, item_id in enumerate(body.item_ids):
        by_id[item_id].position = position
    version = bump_version(db)
    db.commit()
    return _day_response(db, day_id, version)


@router.post("/api/days/{day_id}/items/bulk")
def bulk_add(day_id: str, body: BulkAddIn, db: Session = Depends(get_db)) -> dict:
    """Append several pool ideas at once, ordered by the canonical island tour
    order (ties: score desc, then title) — powers cluster banners and day
    templates."""
    day = _get_day(db, day_id)
    ideas = db.query(Idea).filter(Idea.id.in_(body.idea_ids)).all()
    if len(ideas) != len(set(body.idea_ids)):
        raise _not_found("idea_not_found", "One of those ideas no longer exists.")

    tour_order = {region.id: region.tour_order for region in db.query(Region).all()}
    ideas.sort(
        key=lambda idea: (
            tour_order.get(idea.region_id, 99),
            -idea_score(idea.votes),
            idea.title,
        )
    )
    position = _next_position(day)
    for idea in ideas:
        db.add(
            ScheduleItem(trip_day_id=day.id, idea_id=idea.id, position=position)
        )
        position += 1
    version = bump_version(db)
    db.commit()
    return _day_response(db, day_id, version)
