"""
Shared helpers for the W1 (Campaign / Prescription / Objectives) tests.

Not a conftest — imported explicitly by tests/test_campaign_*.py,
tests/test_prescription_*.py and tests/test_goals_v3.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.models.exercise import Exercise
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession
from app.services import campaign_service
from app.services.condition_service import band_for_score
from app.services.exercise_family_defs import family_for_name
from scripts.import_training_calendar import load_phases as _load_phases

DATA_JS = Path(__file__).resolve().parents[3] / "training-calendar" / "data.js"

# A fixed Monday so every campaign-relative date in these tests is deterministic.
MONDAY = date(2026, 8, 31)


def load_phases() -> List[Dict[str, Any]]:
    return _load_phases(DATA_JS)


def make_user(create_test_user, prefix: str = "w1"):
    return create_test_user(email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com")[0]


def family_exercise(db, name: str, family: Optional[str] = None) -> Exercise:
    """Seed an exercise row with its family assigned (as the migration backfill would)."""
    fam = family or family_for_name(name)
    assert fam, f"{name} resolves to no family — pass family= explicitly"
    ex = Exercise(
        id=str(uuid.uuid4()), name=name, family_id=fam, category="compound",
        primary_muscle="Chest", secondary_muscles=[], is_custom=False, user_id=None,
    )
    db.add(ex)
    db.commit()
    return ex


SetSpec = Tuple  # (weight, reps) | (weight, reps, rpe) | (weight, reps, rpe, is_warmup)


def add_lift(
    db,
    user_id: str,
    day: date,
    blocks: Sequence[Tuple[Exercise, Sequence[SetSpec]]],
    *,
    duration_minutes: int = 60,
    name: Optional[str] = None,
    unit: WeightUnit = WeightUnit.LB,
    instant: Optional[datetime] = None,
    stamp_local: bool = True,
    **fields: Any,
) -> WorkoutSession:
    """A strength session on ``day`` (local) with the given exercises/sets.

    ``instant`` overrides the stored ``date`` (default 10:00 on ``day``);
    ``stamp_local=False`` leaves ``local_date`` NULL to model a legacy row.
    Extra ``fields`` go straight onto the ``WorkoutSession``.
    """
    session = WorkoutSession(
        user_id=user_id, date=instant or datetime.combine(day, time(10, 0)),
        local_date=day if stamp_local else None,
        duration_minutes=duration_minutes, name=name, **fields,
    )
    db.add(session)
    db.flush()
    for order, (exercise, specs) in enumerate(blocks):
        we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=order)
        db.add(we)
        db.flush()
        for n, spec in enumerate(specs, start=1):
            weight, reps = spec[0], spec[1]
            rpe = spec[2] if len(spec) > 2 else None
            warm = bool(spec[3]) if len(spec) > 3 else False
            weight_lb = weight * 2.20462 if unit == WeightUnit.KG else weight
            db.add(Set(
                workout_exercise_id=we.id, weight=weight, weight_unit=unit, weight_lb=weight_lb,
                reps=reps, rpe=rpe, set_number=n, is_warmup=warm,
                e1rm=round(weight_lb * (1 + reps / 30), 2),
            ))
    db.commit()
    return session


def add_run(
    db,
    user_id: str,
    day: date,
    miles: float,
    *,
    activity: str = "Outdoor Run",
    instant: Optional[datetime] = None,
    stamp_local: bool = True,
    **fields: Any,
) -> WorkoutSession:
    """A cardio session of ``miles`` on ``day``; same ``instant``/``stamp_local`` knobs as ``add_lift``."""
    values: Dict[str, Any] = dict(
        duration_minutes=int(miles * 10), duration_seconds=int(miles * 600),
        activity_type=activity, distance_meters=miles * 1609.344, hr_source="apple_watch",
    )
    values.update(fields)
    session = WorkoutSession(
        user_id=user_id, date=instant or datetime.combine(day, time(7, 0)),
        local_date=day if stamp_local else None, **values,
    )
    db.add(session)
    db.commit()
    return session


def import_plan(db, user_id: str, start: date = MONDAY, phases=None, *, name: str = "Run Base + Strength"):
    campaign, warnings, _ = campaign_service.import_campaign(
        db, user_id, name=name, phases=phases or load_phases(), start_date=start, client_date=start,
    )
    db.commit()
    return campaign, warnings


def condition(score: int) -> Dict[str, Any]:
    return {"score": score, "band": band_for_score(score), "generated_at": "", "inputs": [], "muscles_cooling": []}


def fake_condition(monkeypatch, score: int, module: str = "app.api.hunts"):
    import importlib
    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, "compute_condition", lambda db, user_id, client_date=None, user_age=None: condition(score))


def hunt_for(db, user_id: str, day: date):
    return campaign_service.hunt_on(db, user_id, day)


def sat(week: int = 0) -> date:
    return MONDAY + timedelta(days=5 + 7 * week)


def sun(week: int = 0) -> date:
    return MONDAY + timedelta(days=6 + 7 * week)


def weekday(offset: int, week: int = 0) -> date:
    return MONDAY + timedelta(days=offset + 7 * week)
