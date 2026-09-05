"""
Seed helpers and cross-workstream fakes for the W3 (Coach) tests.

``seed_four_weeks`` builds a four-week athlete directly from W0's models
(no W1 import): eight lift sessions (Saturday squat 5×5 progressing
225→240, Sunday bench 5×5), twelve runs with ``hr_zone_seconds`` and
``distance_meters``, three weeks of WHOOP ``DailyActivity``, an active
campaign with planned hunts for the four past weeks plus next week, one
strength objective and a squat PR each week.

``install_fake_w1`` / ``install_fake_w2`` put fake modules in ``sys.modules``
for the W1 / W2 services so these tests never depend on the other
workstreams' real behaviour (the shared brief's rule). ``install_fake_model``
replaces the Anthropic client factory.
"""
from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from sqlalchemy import func

from app.core.e1rm import calculate_e1rm
from app.models.activity import DailyActivity
from app.models.campaign import (
    Campaign,
    CampaignArc,
    CampaignSource,
    CampaignStatus,
    HuntTemplate,
    HuntType,
    PlannedHunt,
    PlannedHuntStatus,
)
from app.models.exercise import Exercise
from app.models.goal import Goal, GoalKind, GoalStatus
from app.models.pr import PR, PRType
from app.models.user import UserProfile
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession

METERS_PER_MILE = 1609.344
SQUAT_WEIGHTS = (225, 230, 235, 240)
BENCH_WEIGHTS = {
    "clean": (185, 190, 195, 200),
    "held": (195, 195, 195, 195),
}
# weekday -> miles for the base week (Tue easy, Thu easy, Fri long)
RUN_PLAN = {1: 2.5, 3: 3.0, 4: 4.5}
WEEK_TARGETS = (8.0, 9.0, 10.0, 11.0, 12.0)   # four past weeks + next week
PACE_SEC_PER_MILE = 570


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def last_completed_week() -> date:
    """Monday of the most recent fully completed ISO week (never rots)."""
    return monday_of(date.today()) - timedelta(days=7)


@dataclass
class Seeded:
    user: Any
    week_start: date
    week_end: date
    weeks: List[date]
    next_week: date
    squat: Exercise
    bench: Exercise
    campaign: Campaign
    arc: CampaignArc
    templates: Dict[int, HuntTemplate] = field(default_factory=dict)
    hunts: Dict[date, PlannedHunt] = field(default_factory=dict)
    sessions: Dict[date, WorkoutSession] = field(default_factory=dict)
    goal: Optional[Goal] = None


def _lift_session(db, user_id: str, day: date, exercise: Exercise, weight: float, *,
                  rpe: int = 8, name: str, warmup: bool = False) -> WorkoutSession:
    session = WorkoutSession(
        user_id=user_id,
        date=datetime.combine(day, time.min),
        local_date=day,
        name=name,
        duration_minutes=60,
        session_rpe=rpe,
    )
    db.add(session)
    db.flush()
    we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    number = 1
    if warmup:
        db.add(Set(
            workout_exercise_id=we.id, weight=135, weight_lb=135, weight_unit=WeightUnit.LB,
            reps=5, set_number=number, is_warmup=True, e1rm=round(calculate_e1rm(135, 5), 2),
        ))
        number += 1
    for _ in range(5):
        db.add(Set(
            workout_exercise_id=we.id, weight=weight, weight_lb=weight, weight_unit=WeightUnit.LB,
            reps=5, rpe=rpe, set_number=number, e1rm=round(calculate_e1rm(weight, 5), 2),
        ))
        number += 1
    db.flush()
    return session


def _run_session(db, user_id: str, day: date, miles: float) -> WorkoutSession:
    secs = int(miles * PACE_SEC_PER_MILE)
    session = WorkoutSession(
        user_id=user_id,
        date=datetime.combine(day, time.min),
        local_date=day,
        name="Run",
        duration_minutes=round(secs / 60),
        duration_seconds=secs,
        activity_type="Outdoor Run",
        distance_meters=round(miles * METERS_PER_MILE, 1),
        hr_source="apple_watch",
        avg_heart_rate=148,
        peak_heart_rate=171,
        hr_zone_seconds={"z1": 120, "z2": int(secs * 0.7), "z3": int(secs * 0.25), "z4": 0, "z5": 0},
    )
    db.add(session)
    db.flush()
    return session


def seed_four_weeks(
    db,
    user,
    *,
    week_start: Optional[date] = None,
    bench: str = "clean",
    run_multiplier_last_week: float = 1.0,
    low_sleep_nights: int = 0,
    campaign: bool = True,
) -> Seeded:
    """Seed the four-week athlete ending on the week of ``week_start``.

    ``bench``: ``clean`` (progressing) or ``held`` (four weeks at 195).
    ``run_multiplier_last_week`` scales the target week's runs (ramp-high).
    ``low_sleep_nights``: nights under 6 h in the target week (Tue onwards).
    """
    week_start = monday_of(week_start or last_completed_week())
    weeks = [week_start - timedelta(weeks=3 - i) for i in range(4)]
    week_end = week_start + timedelta(days=6)
    next_week = week_end + timedelta(days=1)

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is not None:
        profile.age = 32
        profile.sex = "M"
        profile.bodyweight_lb = 176.0
        profile.injury_notes = "Left knee: no deep lunges."

    squat = Exercise(name="Barbell Back Squat", family_id="back_squat", category="compound",
                     primary_muscle="quads", secondary_muscles=["glutes", "hamstrings"])
    bench_ex = Exercise(name="Barbell Bench Press", family_id="bench_press", category="compound",
                        primary_muscle="chest", secondary_muscles=["triceps", "shoulders"])
    db.add_all([squat, bench_ex])
    db.flush()

    seeded = Seeded(
        user=user, week_start=week_start, week_end=week_end, weeks=weeks, next_week=next_week,
        squat=squat, bench=bench_ex, campaign=None, arc=None,  # type: ignore[arg-type]
    )

    if campaign:
        camp = Campaign(
            user_id=user.id, name="Fall Base", goal="Sub-50 10K and a 315 squat",
            start_date=weeks[0], status=CampaignStatus.ACTIVE.value,
            source=CampaignSource.IMPORT.value, overrides=None,
        )
        db.add(camp)
        db.flush()
        arc = CampaignArc(
            campaign_id=camp.id, index=0, name="Base", weeks=8, run_miles_min=8.0,
            run_miles_max=14.0, long_run_miles=5.0, deload_every_n_weeks=4, deload_factor=0.75,
        )
        db.add(arc)
        db.flush()
        template_specs = {
            1: (HuntType.RUN.value, "Easy run", [{"run": "easy", "miles": [2, 3]}]),
            3: (HuntType.RUN.value, "Easy run", [{"run": "easy", "miles": [2.5, 3.5]}]),
            4: (HuntType.RUN.value, "Long run", [{"run": "long", "miles": "arc"}]),
            5: (HuntType.LIFT.value, "Heavy Squat", [{
                "family": "back_squat", "sets": 5, "reps": [5, 5], "role": "main",
                "progression": "linear", "increment_lb": 5, "rpe_cap": 8,
            }]),
            6: (HuntType.LIFT.value, "Bench", [{
                "family": "bench_press", "sets": 5, "reps": [5, 5], "role": "main",
                "progression": "linear", "increment_lb": 5, "rpe_cap": 8,
            }]),
        }
        for weekday, (kind, title, items) in template_specs.items():
            tpl = HuntTemplate(arc_id=arc.id, weekday=weekday, type=kind, title=title, items=items)
            db.add(tpl)
            seeded.templates[weekday] = tpl
        db.flush()
        for i, monday in enumerate(weeks + [next_week]):
            for weekday, tpl in seeded.templates.items():
                hunt = PlannedHunt(
                    user_id=user.id, campaign_id=camp.id, arc_id=arc.id, template_id=tpl.id,
                    date=monday + timedelta(days=weekday), week_start=monday,
                    week_target_miles=WEEK_TARGETS[i], status=PlannedHuntStatus.PLANNED.value,
                )
                db.add(hunt)
                seeded.hunts[hunt.date] = hunt
        db.flush()
        seeded.campaign = camp
        seeded.arc = arc

    bench_weights = BENCH_WEIGHTS[bench]
    for i, monday in enumerate(weeks):
        saturday, sunday = monday + timedelta(days=5), monday + timedelta(days=6)
        squat_session = _lift_session(db, user.id, saturday, squat, SQUAT_WEIGHTS[i],
                                      name="Heavy Squat", warmup=True)
        bench_session = _lift_session(db, user.id, sunday, bench_ex, bench_weights[i],
                                      name="Bench", rpe=9 if bench == "held" else 8)
        seeded.sessions[saturday] = squat_session
        seeded.sessions[sunday] = bench_session
        scale = WEEK_TARGETS[i] / 10.0
        if monday == week_start:
            scale *= run_multiplier_last_week
        for weekday, base in RUN_PLAN.items():
            day = monday + timedelta(days=weekday)
            seeded.sessions[day] = _run_session(db, user.id, day, round(base * scale, 2))
        # PR each Saturday so the target week's PR has a previous best to beat.
        db.add(PR(
            user_id=user.id, exercise_id=squat.id, pr_type=PRType.E1RM,
            value=round(calculate_e1rm(SQUAT_WEIGHTS[i], 5), 2), weight=SQUAT_WEIGHTS[i], reps=5,
            achieved_at=datetime.combine(saturday, time(10, 0)),
        ))
    db.flush()

    if campaign:
        for day, session in seeded.sessions.items():
            hunt = seeded.hunts.get(day)
            if hunt is not None:
                hunt.status = PlannedHuntStatus.DONE.value
                hunt.session_id = session.id
        db.flush()

    low_days = {week_start + timedelta(days=1 + k) for k in range(low_sleep_nights)}
    for k in range(21):
        day = week_end - timedelta(days=k)
        low = day in low_days
        db.add(DailyActivity(
            user_id=user.id, date=day, source="whoop",
            sleep_hours=5.5 if low else 7.3, hrv=48 if low else 62,
            resting_heart_rate=56 if low else 52, recovery_score=45 if low else 74,
            strain=11.5, steps=8000,
        ))
    db.flush()

    goal = Goal(
        user_id=user.id, exercise_id=bench_ex.id, kind=GoalKind.STRENGTH.value,
        campaign_id=seeded.campaign.id if campaign else None,
        target_weight=225, target_reps=1, weight_unit="lb",
        deadline=week_end + timedelta(weeks=8),
        starting_e1rm=round(calculate_e1rm(bench_weights[0], 5), 2),
        current_e1rm=round(calculate_e1rm(bench_weights[-1], 5), 2),
        status=GoalStatus.ACTIVE.value, deadline_extensions=0,
    )
    db.add(goal)
    db.commit()
    seeded.goal = goal
    return seeded


# ---------------------------------------------------------------------------
# Cross-workstream fakes
# ---------------------------------------------------------------------------


def _install_module(monkeypatch, name: str, module: Optional[types.ModuleType]) -> None:
    """Put ``module`` (or ``None`` = "absent") under ``name`` in sys.modules
    and mirror it on the ``app.services`` package attribute so both import
    styles resolve to the fake."""
    import app.services as services_pkg

    monkeypatch.setitem(sys.modules, name, module)
    attr = name.rsplit(".", 1)[-1]
    if module is None:
        monkeypatch.delattr(services_pkg, attr, raising=False)
    else:
        monkeypatch.setattr(services_pkg, attr, module, raising=False)


def install_fake_w1(
    monkeypatch,
    *,
    verdicts: Optional[List[Dict[str, Any]]] = None,
    goal_flags: Optional[List[Dict[str, Any]]] = None,
    week_miles: Optional[Dict[date, float]] = None,
) -> List[tuple]:
    """Fake ``campaign_service`` / ``prescription_service`` / W1's
    ``goal_service`` additions. Returns the list the appliers record into."""
    applied: List[tuple] = []

    cs = types.ModuleType("app.services.campaign_service")

    def get_active_campaign(db, user_id):
        return (
            db.query(Campaign)
            .filter(Campaign.user_id == user_id, Campaign.status == CampaignStatus.ACTIVE.value)
            .order_by(Campaign.start_date.desc())
            .first()
        )

    def materialize_range(db, user_id, start, end):
        return (
            db.query(PlannedHunt)
            .filter(PlannedHunt.user_id == user_id, PlannedHunt.date >= start, PlannedHunt.date <= end)
            .order_by(PlannedHunt.date)
            .all()
        )

    def week_target_miles(db, campaign, ws):
        if week_miles and ws in week_miles:
            return week_miles[ws]
        return (
            db.query(func.max(PlannedHunt.week_target_miles))
            .filter(PlannedHunt.campaign_id == campaign.id, PlannedHunt.week_start == ws)
            .scalar()
        )

    def _applier(name):
        def fn(db, campaign, *args):
            applied.append((name, args))
            return ["ph-applied"]
        return fn

    cs.get_active_campaign = get_active_campaign
    cs.materialize_range = materialize_range
    cs.week_target_miles = week_target_miles
    for name in ("set_progression", "set_week_miles", "deload_now", "swap_days", "extend_arc", "change_reps"):
        setattr(cs, f"apply_{name}", _applier(name))
    _install_module(monkeypatch, "app.services.campaign_service", cs)

    ps = types.ModuleType("app.services.prescription_service")
    ps.progression_verdicts = lambda db, uid, ws: [dict(v) for v in (verdicts or [])]
    _install_module(monkeypatch, "app.services.prescription_service", ps)

    from app.services import goal_service

    monkeypatch.setattr(goal_service, "goal_flags", lambda db, uid: [dict(f) for f in (goal_flags or [])], raising=False)

    def extend_goal_deadline(db, uid, goal_id, deadline):
        goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == uid).first()
        if goal is None:
            raise ValueError("Objective not found.")
        if (goal.deadline_extensions or 0) > 0:
            raise ValueError("Deadline already extended once.")
        applied.append(("set_goal_deadline", (goal_id, deadline)))
        goal.deadline = deadline
        goal.deadline_extensions = 1
        db.flush()
        return goal

    monkeypatch.setattr(goal_service, "extend_goal_deadline", extend_goal_deadline, raising=False)
    return applied


def remove_w1(monkeypatch) -> None:
    """Make every W1 import fail (ImportError) to exercise the fallbacks."""
    _install_module(monkeypatch, "app.services.campaign_service", None)
    _install_module(monkeypatch, "app.services.prescription_service", None)
    from app.services import goal_service

    monkeypatch.delattr(goal_service, "goal_flags", raising=False)
    monkeypatch.delattr(goal_service, "extend_goal_deadline", raising=False)


def install_fake_w2(
    monkeypatch,
    *,
    flags: tuple = (),
    miles_7d: Optional[float] = 10.0,
    miles_plan_7d: Optional[float] = 11.0,
    run_acwr: Optional[float] = 1.05,
    longest_run_7d: Optional[float] = 4.5,
    series: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    tl = types.ModuleType("app.services.training_load_service")
    state = {
        "run_acute_7d": 120.0, "run_chronic_28d": 110.0, "run_acwr": run_acwr,
        "total_acwr": 1.1, "band": "green", "miles_7d": miles_7d, "miles_plan_7d": miles_plan_7d,
        "longest_run_7d": longest_run_7d, "flags": list(flags), "series": series or [],
    }
    tl.get_load_state = lambda db, uid, as_of: dict(state, as_of=as_of.isoformat())
    tl.guard_flags_for_date = lambda db, uid, d: list(flags)
    _install_module(monkeypatch, "app.services.training_load_service", tl)
    return state


def remove_w2(monkeypatch) -> None:
    _install_module(monkeypatch, "app.services.training_load_service", None)


# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------


class FakeUsage:
    input_tokens = 9000
    output_tokens = 800
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 8500


class FakeResponse:
    def __init__(self, parsed, stop_reason: str = "end_turn"):
        self.parsed_output = parsed
        self.stop_reason = stop_reason
        self.stop_details = None
        self.usage = FakeUsage()
        self.model = "claude-opus-5"


def install_fake_model(monkeypatch, outcome: Any) -> List[Dict[str, Any]]:
    """Replace the client factory. ``outcome`` is a model-output dict, an
    exception instance to raise, or ``"refusal"``. Returns the recorded
    ``parse`` kwargs (one entry per call)."""
    from app.schemas.coach import DebriefModelOutput
    from app.services import debrief_service

    calls: List[Dict[str, Any]] = []

    def parse(**kwargs):
        calls.append(kwargs)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == "refusal":
            return FakeResponse(None, stop_reason="refusal")
        return FakeResponse(DebriefModelOutput.model_validate(outcome))

    client = MagicMock()
    client.beta.messages.parse.side_effect = parse
    monkeypatch.setattr(debrief_service, "build_anthropic_client", lambda: client)
    return calls


def model_output(
    ctx: Dict[str, Any],
    *,
    adjustments: Optional[List[Dict[str, Any]]] = None,
    concerns: Optional[List[Dict[str, str]]] = None,
    summary: str = "Week ran close to plan. One thing mattered.",
    focus: str = "Run the plan as written.",
) -> Dict[str, Any]:
    """A plausible model reply: echoes the engine's concerns and, by default,
    its candidate ops as adjustments."""
    candidates = ctx.get("candidates") or {}
    if adjustments is None:
        adjustments = []
        for op in candidates.get("candidate_ops") or []:
            adj = {k: v for k, v in op.items() if k != "numbers"}
            adjustments.append(adj)
    if concerns is None:
        concerns = [{"flag": c["flag"], "text": c["text"]} for c in candidates.get("concerns") or []]
    return {
        "summary": summary,
        "concerns": concerns,
        "adjustments": adjustments,
        "next_week_focus": focus,
    }


def sentence_count(text: str) -> int:
    import re

    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])
