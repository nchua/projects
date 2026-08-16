"""Idempotent seed — runs on every boot via the Railway startCommand.

Reference data (regions, drive times) is upserted so curation tweaks ship as
ordinary commits. Content (members, days, ideas) is insert-if-missing so user
edits are never overwritten. Missing seed JSON files are skipped, not fatal.
"""
import json
from datetime import date, time
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.versioning import bump_version
from app.models.day import TripDay
from app.models.idea import Idea
from app.models.member import Member
from app.models.region import DriveTime, Region

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"

MEMBERS = [
    ("Nick", "#0B7285"),
    ("Erica", "#D6336C"),
    ("Ellyn", "#2F9E44"),
    ("Mom", "#E8A13C"),
    ("Dad", "#1864AB"),
]

# (date, label, start_time, end_time, notes) — arrival night ends late by
# definition, so its window is 21:00-23:30 rather than the default 21:30 end
# (which would flag any dinner stop as "overpacked").
DAYS = [
    (date(2026, 8, 26), "Arrival night", time(21, 0), time(23, 30), "Land ~9pm — dinner near the hotel"),
    (date(2026, 8, 27), None, time(8, 30), time(21, 30), None),
    (date(2026, 8, 28), None, time(8, 30), time(21, 30), None),
    (date(2026, 8, 29), None, time(8, 30), time(21, 30), None),
    (date(2026, 8, 30), None, time(8, 30), time(21, 30), "Nick flies out 10pm"),
    (date(2026, 8, 31), "Last day", time(9, 0), time(21, 30), "Checkout — flights home (4 travelers)"),
]


def _load(name: str) -> list[dict]:
    path = SEED_DIR / name
    if not path.exists():
        print(f"seed: {name} not found, skipping")
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def seed_regions(db: Session) -> bool:
    changed = False
    for row in _load("regions.json"):
        region = db.get(Region, row["id"])
        if region is None:
            db.add(Region(**row))
            changed = True
        elif (
            region.name != row["name"]
            or region.sort_order != row["sort_order"]
            or region.tour_order != row["tour_order"]
        ):
            region.name = row["name"]
            region.sort_order = row["sort_order"]
            region.tour_order = row["tour_order"]
            changed = True
    return changed


def seed_drive_times(db: Session) -> bool:
    changed = False
    for row in _load("drive_times.json"):
        flags = ",".join(row.get("flags", []))
        existing = db.get(
            DriveTime, {"region_a": row["region_a"], "region_b": row["region_b"]}
        )
        if existing is None:
            db.add(
                DriveTime(
                    region_a=row["region_a"],
                    region_b=row["region_b"],
                    minutes=row["minutes"],
                    flags=flags,
                )
            )
            changed = True
        elif existing.minutes != row["minutes"] or existing.flags != flags:
            existing.minutes = row["minutes"]
            existing.flags = flags
            changed = True
    return changed


def seed_members(db: Session) -> bool:
    changed = False
    for name, color in MEMBERS:
        exists = (
            db.query(Member).filter(func.lower(Member.name) == name.lower()).first()
        )
        if exists is None:
            db.add(Member(name=name, color=color))
            changed = True
    return changed


def seed_days(db: Session) -> bool:
    changed = False
    for sort_order, (day_date, label, start, end, notes) in enumerate(DAYS):
        exists = db.query(TripDay).filter(TripDay.date == day_date).first()
        if exists is None:
            db.add(
                TripDay(
                    date=day_date,
                    label=label,
                    start_time=start,
                    end_time=end,
                    notes=notes,
                    sort_order=sort_order,
                )
            )
            changed = True
    return changed


def _seed_ideas(db: Session, rows: list[dict], kind: str) -> bool:
    changed = False
    for row in rows:
        exists = (
            db.query(Idea)
            .filter(func.lower(Idea.title) == row["title"].lower(), Idea.kind == kind)
            .first()
        )
        if exists is not None:
            continue
        db.add(
            Idea(
                title=row["title"],
                kind=kind,
                region_id=row["region_id"],
                duration_min=row.get("duration_min")
                or (75 if kind == "restaurant" else 90),
                yelp_url=row.get("yelp_url"),
                maps_url=row.get("maps_url"),
                notes=row.get("notes"),
                recommended_by=row.get("recommended_by"),
                reservation_rule=row.get("reservation_rule"),
                closed_days=",".join(row.get("closed_days", [])),
                difficulty=row.get("difficulty"),
                best_time=row.get("best_time"),
                meal_tags=",".join(row.get("meal_tags", [])),
            )
        )
        changed = True
    return changed


def run() -> None:
    db = SessionLocal()
    try:
        changed = False
        # These tables are linked only by bare FKs (no relationship()), so the
        # unit of work won't order their inserts — flush each layer before the
        # next one references it.
        changed |= seed_regions(db)
        db.flush()
        changed |= seed_drive_times(db)
        db.flush()
        changed |= seed_members(db)
        changed |= seed_days(db)
        changed |= _seed_ideas(db, _load("activities.json"), "activity")
        changed |= _seed_ideas(db, _load("restaurants.json"), "restaurant")
        if changed:
            bump_version(db)
        db.commit()
        print(f"seed: done (changed={changed})")
    finally:
        db.close()


if __name__ == "__main__":
    run()
