"""One-shot render payload + the version poll target."""
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.api.serialize import (
    build_drive_lookup,
    day_out,
    idea_out,
    member_out,
    region_out,
    scheduled_day_ids_by_idea,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.versioning import current_version
from app.models.day import ScheduleItem, TripDay
from app.models.idea import Idea
from app.models.member import Member
from app.models.region import Region

router = APIRouter()

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed"


@lru_cache(maxsize=1)
def day_templates() -> list[dict]:
    """Read-only seed archetypes ('North Shore Classic Loop', ...); served
    straight from JSON — no DB table, no editor."""
    path = SEED_DIR / "day_templates.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/version")
def version(db: Session = Depends(get_db)) -> dict:
    return {"version": current_version(db)}


@router.get("/api/bootstrap")
def bootstrap(db: Session = Depends(get_db)) -> dict:
    drive_lookup, drive_rows = build_drive_lookup(db)
    days = (
        db.query(TripDay)
        .options(joinedload(TripDay.items).joinedload(ScheduleItem.idea))
        .all()
    )
    days.sort(key=lambda d: (d.date is None, d.date or d.created_at, d.sort_order))
    ideas = db.query(Idea).options(joinedload(Idea.votes)).all()
    scheduled = scheduled_day_ids_by_idea(db)

    return {
        "version": current_version(db),
        "app_name": settings.APP_NAME,
        "members": [
            member_out(member)
            for member in db.query(Member).order_by(Member.created_at).all()
        ],
        "regions": [
            region_out(region)
            for region in db.query(Region).order_by(Region.sort_order).all()
        ],
        "drive_times": drive_rows,
        "days": [day_out(day, drive_lookup) for day in days],
        "ideas": [idea_out(idea, scheduled.get(idea.id, [])) for idea in ideas],
        "day_templates": day_templates(),
    }
