"""Backfill exercise families (ARISE v3 spec §4.2) — fallback, prefer ``/admin/ui``.

The owner console runs the same thing as ``POST /admin/maintenance/exercise-families``
(dry run by default, audited on apply; control-plane spec §7.3). Use this
script only when the console is unreachable.

Run from fitness-app/backend: venv/bin/python scripts/backfill_exercise_families.py

Upserts the committed family rows (``exercise_family_defs.FAMILY_DEFS``) and
assigns ``exercises.family_id`` for every row — seeded rows by canonical /
alias name (inheriting through ``canonical_id``), custom rows by exact
case-insensitive name match. Idempotent: a re-run reports 0 changes. Prints
counts plus the exercise names still without a family; never prints emails.

The ``v3_exercise_families`` migration already does the seeded half on
deploy; this script exists for custom exercises and for dict updates.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.models  # noqa: E402, F401 — register every model
from app.models.exercise import Exercise  # noqa: E402
from app.services.exercise_family_service import (  # noqa: E402
    assign_family_ids,
    ensure_families,
)


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set")
        return 1

    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    try:
        families_changed = ensure_families(session)
        exercises_updated = assign_family_ids(session, include_custom=True)

        total = session.query(Exercise).count()
        assigned = session.query(Exercise).filter(Exercise.family_id.isnot(None)).count()
        unresolved = (
            session.query(Exercise.name, Exercise.is_custom)
            .filter(Exercise.family_id.is_(None))
            .order_by(Exercise.is_custom.desc(), Exercise.name)
            .all()
        )

        print(f"families inserted/updated: {families_changed}")
        print(f"exercises updated: {exercises_updated}")
        print(f"exercises with a family: {assigned}/{total}")
        print(f"exercises still NULL: {len(unresolved)}")
        for name, is_custom in unresolved:
            print(f"  {'custom' if is_custom else 'seed  '}  {name}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
