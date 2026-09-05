"""
Athlete context builder (ARISE v3 spec §8.2).

Composes the existing services into one JSON document the Coach reads:
campaign + next hunts, four weeks of sessions, per-family e1RM trends,
Condition, load, wearable series, objectives, the engine's candidate ops and
the profile. Key order and numeric precision are fixed (weights 1 dp, miles
and ratios 2 dp) so identical weeks hash identically (``context_hash``).

Every number in the model's prompt comes from here; the model never sees a
number the engine did not compute.

Cross-workstream calls (W1 ``campaign_service`` / ``goal_service``, W2
``training_load_service``) are imported lazily with a documented neutral
fallback so this module imports while those land in parallel.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.core.utils import derive_local_date, ensure_utc
from app.models.bodyweight import BodyweightEntry
from app.models.campaign import Campaign, CampaignArc, CampaignStatus, PlannedHunt
from app.models.coach import CoachOutput, CoachOutputKind
from app.models.gate import GateStatus
from app.models.goal import Goal, GoalStatus
from app.models.user import UserProfile
from app.models.workout import WorkoutExercise, WorkoutSession
from app.services.activity_series import daily_activity_series
from app.services.condition_service import compute_condition
from app.services.exercise_family_service import families_for_user
from app.services.gate_service import get_gate_history, get_live_gates
from app.services.trend_service import (
    projected_e1rm,
    weekly_best_e1rm_series,
    weekly_slope,
)
from app.services.weekly_report_service import _get_goal_progress_reports, _get_week_prs

logger = logging.getLogger(__name__)

CONTEXT_VERSION = "ctx_v1"
# Spec §8.2 targets ≈ 6–8K tokens; the hard ceiling the tests assert.
TOKEN_BUDGET = 12_000
SESSION_WEEKS = 4
FAMILY_SERIES_WEEKS = 12
WEARABLE_DAYS = 14
NEXT_HUNTS = 7
PROJECTION_DAYS = 14
METERS_PER_MILE = 1609.344
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_RUN_KEYWORDS = ("run", "running", "jog")

# Fixed top-level key order (spec §8.2 "fixed key order").
SECTION_ORDER = (
    "version",
    "week_start",
    "week_end",
    "as_of",
    "campaign",
    "sessions_4w",
    "families",
    "condition_today",
    "load",
    "wearable_14d",
    "objectives",
    "candidates",
    "profile",
    "truncated",
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _r1(value: Any) -> Optional[float]:
    return None if value is None else round(float(value), 1)


def _r2(value: Any) -> Optional[float]:
    return None if value is None else round(float(value), 2)


def _num(value: Any) -> Any:
    """Compact number for set strings: ``225`` not ``225.0``, else 1 dp."""
    if value is None:
        return None
    rounded = round(float(value), 1)
    return int(rounded) if rounded == int(rounded) else rounded


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def session_local_day(session: WorkoutSession) -> date:
    """``local_date`` is authoritative; fall back per ``derive_local_date``.

    A non-midnight legacy row has no recoverable local day without a client
    tz offset, which the coach does not have — its UTC calendar day is used.
    """
    if session.local_date is not None:
        return session.local_date
    derived = derive_local_date(session.date)
    if derived is not None:
        return derived
    return session.date.date()


def is_run(activity_type: Optional[str]) -> bool:
    if not activity_type:
        return False
    lowered = activity_type.lower()
    return any(k in lowered for k in _RUN_KEYWORDS)


def _set_string(s: Any) -> str:
    weight = s.weight_lb if getattr(s, "weight_lb", None) is not None else s.weight
    core = f"{_num(weight)}x{s.reps}"
    if getattr(s, "is_bodyweight", False):
        core = f"bw+{_num(weight)}x{s.reps}" if weight else f"bwx{s.reps}"
    if s.rpe is not None:
        core += f"@{s.rpe}"
    return core


def load_sessions(
    db: Session, user_id: str, start: date, end: date
) -> List[Tuple[date, WorkoutSession]]:
    """Non-deleted sessions whose local day is in [start, end], oldest first.

    The query pads a day each side so a legacy UTC-instant row near an edge
    is not lost before the local-day bucketing decides.
    """
    q_start = datetime.combine(start, time.min) - timedelta(days=1)
    q_end = datetime.combine(end, time.max) + timedelta(days=1)
    sessions = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.exercise),
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets),
        )
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= q_start,
            WorkoutSession.date <= q_end,
        )
        .order_by(WorkoutSession.date.asc())
        .all()
    )
    out: List[Tuple[date, WorkoutSession]] = []
    for s in sessions:
        day = session_local_day(s)
        if start <= day <= end:
            out.append((day, s))
    return out


def run_miles(session: WorkoutSession) -> Optional[float]:
    if session.distance_meters is None:
        return None
    return _r2(session.distance_meters / METERS_PER_MILE)


def run_pace_sec(session: WorkoutSession) -> Optional[int]:
    secs = session.duration_seconds or (
        session.duration_minutes * 60 if session.duration_minutes else None
    )
    if secs and session.distance_meters and session.distance_meters >= 400:
        return round(secs / (session.distance_meters / METERS_PER_MILE))
    return None


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------


def active_campaign(db: Session, user_id: str) -> Optional[Campaign]:
    """W1's ``get_active_campaign``; falls back to a direct read of the row.

    Cross-workstream lazy import (W1). Fallback: the newest ``active``
    campaign row — read-only, same result once W1 lands.
    """
    try:
        from app.services.campaign_service import get_active_campaign
    except ImportError:
        get_active_campaign = None  # type: ignore[assignment]
    if get_active_campaign is not None:
        return get_active_campaign(db, user_id)
    return (
        db.query(Campaign)
        .options(joinedload(Campaign.arcs))
        .filter(Campaign.user_id == user_id, Campaign.status == CampaignStatus.ACTIVE.value)
        .order_by(desc(Campaign.start_date))
        .first()
    )


def planned_hunts_between(
    db: Session, user_id: str, start: date, end: date, *, materialize: bool = False
) -> List[PlannedHunt]:
    """Planned hunts with ``date`` in [start, end], ordered by date.

    With ``materialize=True`` W1's ``materialize_range`` runs first so next
    week's hunts exist. Cross-workstream lazy import (W1); fallback: the rows
    already present.
    """
    if materialize:
        try:
            from app.services.campaign_service import materialize_range
        except ImportError:
            materialize_range = None  # type: ignore[assignment]
        if materialize_range is not None:
            try:
                materialize_range(db, user_id, start, end)
            except Exception as exc:  # never let materialization blank the debrief
                logger.warning("materialize_range failed for %s: %s", user_id, exc)
    return (
        db.query(PlannedHunt)
        .options(joinedload(PlannedHunt.template))
        .filter(
            PlannedHunt.user_id == user_id,
            PlannedHunt.date >= start,
            PlannedHunt.date <= end,
        )
        .order_by(PlannedHunt.date.asc(), PlannedHunt.created_at.asc())
        .all()
    )


def week_target_miles(
    db: Session, campaign: Optional[Campaign], week_start: date
) -> Optional[float]:
    """W1's arc ramp value for the week; fallback reads the rows' stamp.

    Cross-workstream lazy import (W1). Fallback: the max
    ``planned_hunts.week_target_miles`` stamped on that week's rows (the
    same number W2 reads for ``miles_plan_7d``), else None.
    """
    if campaign is None:
        return None
    try:
        from app.services.campaign_service import week_target_miles as _wtm
    except ImportError:
        _wtm = None  # type: ignore[assignment]
    if _wtm is not None:
        try:
            return _r2(_wtm(db, campaign, week_start))
        except Exception as exc:
            logger.warning("week_target_miles failed: %s", exc)
    rows = (
        db.query(PlannedHunt.week_target_miles)
        .filter(
            PlannedHunt.campaign_id == campaign.id,
            PlannedHunt.week_start == week_start,
            PlannedHunt.week_target_miles.isnot(None),
        )
        .all()
    )
    values = [r[0] for r in rows if r[0] is not None]
    return _r2(max(values)) if values else None


def arc_for_week(campaign: Campaign, week_start: date) -> Tuple[Optional[CampaignArc], int, int]:
    """(arc, week_in_arc 1-based, week_in_campaign 1-based) for a Monday."""
    campaign_monday = monday_of(campaign.start_date)
    week_index = (week_start - campaign_monday).days // 7  # 0-based
    arcs = sorted(campaign.arcs or [], key=lambda a: a.index)
    cursor = 0
    for arc in arcs:
        if week_index < cursor + arc.weeks:
            return arc, week_index - cursor + 1, week_index + 1
        cursor += arc.weeks
    last = arcs[-1] if arcs else None
    return last, (week_index - cursor + (last.weeks if last else 0) + 1), week_index + 1


def deload_week(campaign: Campaign, arc: Optional[CampaignArc], week_in_arc: int, week_start: date) -> bool:
    overrides = campaign.overrides or {}
    if week_start.isoformat() in (overrides.get("deload_weeks") or []):
        return True
    if arc is None or not arc.deload_every_n_weeks:
        return False
    return week_in_arc > 0 and week_in_arc % arc.deload_every_n_weeks == 0


def _summarize_prescription(hunt: PlannedHunt) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Top-set-per-exercise summary from the prescription JSON (§15.3), or
    the template's items when the hunt is not prescribed yet."""
    lifts: List[Dict[str, Any]] = []
    run: Optional[Dict[str, Any]] = None
    prescription = hunt.prescription or {}
    if prescription:
        for ex in prescription.get("exercises") or []:
            sets = [s for s in (ex.get("sets") or []) if not s.get("is_warmup")]
            if not sets:
                continue
            top = max(sets, key=lambda s: (s.get("target_weight_lb") or 0))
            lo, hi = top.get("target_reps_lo"), top.get("target_reps_hi")
            lifts.append({
                "family": ex.get("family_id"),
                "role": ex.get("role"),
                "sets": len(sets),
                "reps": lo if lo == hi or hi is None else f"{lo}-{hi}",
                "weight_lb": _r1(top.get("target_weight_lb")),
            })
        pr_run = prescription.get("run")
        if pr_run:
            run = {
                "kind": pr_run.get("kind"),
                "miles": _r2(pr_run.get("miles")),
                "hr_cap": pr_run.get("hr_cap_bpm"),
            }
        return lifts, run
    template = hunt.template
    for item in (template.items if template else None) or []:
        if "family" in item:
            reps = item.get("reps")
            if isinstance(reps, list):
                reps = reps[0] if len(reps) > 1 and reps[0] == reps[-1] else "-".join(str(r) for r in reps)
            lifts.append({
                "family": item["family"],
                "role": item.get("role"),
                "sets": item.get("sets"),
                "reps": reps,
                "weight_lb": None,
            })
        elif "run" in item:
            miles = item.get("miles")
            run = {
                "kind": item["run"],
                "miles": miles if isinstance(miles, str) else (_r2(miles[-1]) if isinstance(miles, list) and miles else _r2(miles)),
                "hr_cap": None,
            }
    return lifts, run


def campaign_section(
    db: Session, user_id: str, week_start: date, campaign: Optional[Campaign]
) -> Optional[Dict[str, Any]]:
    if campaign is None:
        return None
    week_end = week_start + timedelta(days=6)
    arc, week_in_arc, week_in_campaign = arc_for_week(campaign, week_start)
    next_week = week_end + timedelta(days=1)
    hunts = planned_hunts_between(
        db, user_id, next_week, next_week + timedelta(days=6), materialize=True
    )[:NEXT_HUNTS]
    overrides = campaign.overrides or {}
    next_hunts = []
    for hunt in hunts:
        lifts, run = _summarize_prescription(hunt)
        next_hunts.append({
            "date": hunt.date.isoformat(),
            "weekday": WEEKDAYS[hunt.date.weekday()],
            "type": hunt.template.type if hunt.template else None,
            "title": hunt.template.title if hunt.template else None,
            "status": hunt.status,
            "lifts": lifts,
            "run": run,
        })
    return {
        "name": campaign.name,
        "goal": campaign.goal,
        "start_date": campaign.start_date.isoformat(),
        "arc": {"name": arc.name, "index": arc.index} if arc else None,
        "week_in_arc": week_in_arc,
        "week_in_campaign": week_in_campaign,
        "deload": deload_week(campaign, arc, week_in_arc, week_start),
        "deload_factor": _r2(arc.deload_factor) if arc else None,
        "deload_every_n_weeks": arc.deload_every_n_weeks if arc else None,
        "last_deload_week": overrides.get("last_deload_week"),
        "week_target_miles": week_target_miles(db, campaign, week_start),
        "next_week_target_miles": week_target_miles(db, campaign, next_week),
        "next_hunts": next_hunts,
    }


# ---------------------------------------------------------------------------
# Sessions (4 weeks)
# ---------------------------------------------------------------------------


def sessions_section(db: Session, user_id: str, week_start: date) -> List[Dict[str, Any]]:
    """The last ``SESSION_WEEKS`` ISO weeks, oldest first, bucketed on the
    local day (the same rule ``api/calendar.get_weekly_calendar`` uses)."""
    first_monday = week_start - timedelta(weeks=SESSION_WEEKS - 1)
    week_end = week_start + timedelta(days=6)
    buckets: Dict[date, Dict[str, Any]] = {
        first_monday + timedelta(weeks=i): {"lifts": [], "runs": []}
        for i in range(SESSION_WEEKS)
    }
    for day, s in load_sessions(db, user_id, first_monday, week_end):
        bucket = buckets.get(monday_of(day))
        if bucket is None:
            continue
        exercises = []
        for we in s.workout_exercises:
            working = [st for st in we.sets if not getattr(st, "is_warmup", False)]
            if not working:
                continue
            exercise = we.exercise
            exercises.append({
                "name": exercise.name if exercise else "Unknown",
                "family": exercise.family_id if exercise else None,
                "sets": [_set_string(st) for st in working],
            })
        if exercises:
            bucket["lifts"].append({
                "date": day.isoformat(),
                "name": s.name,
                "rpe": s.session_rpe,
                "exercises": exercises,
            })
            continue
        if s.activity_type is None and s.distance_meters is None:
            continue
        bucket["runs"].append({
            "date": day.isoformat(),
            "type": s.activity_type,
            "is_run": is_run(s.activity_type) or (s.activity_type is None and s.distance_meters is not None),
            "miles": run_miles(s),
            "pace_sec_per_mile": run_pace_sec(s),
            "avg_hr": s.avg_heart_rate,
        })
    weeks = []
    for monday in sorted(buckets):
        b = buckets[monday]
        weeks.append({
            "week_start": monday.isoformat(),
            "run_miles": _r2(sum((r["miles"] or 0.0) for r in b["runs"] if r["is_run"])),
            "lifts": b["lifts"],
            "runs": b["runs"],
        })
    return weeks


# ---------------------------------------------------------------------------
# Families
# ---------------------------------------------------------------------------


def families_section(
    db: Session,
    user_id: str,
    week_start: date,
    campaign: Optional[Campaign],
    extra_families: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Per family: 12-week weekly-best e1RM series, 6-week slope, 14-day
    projection, best e1RM in the campaign. Every family an adjustment may
    name must be here — the validator checks against this list, so families
    in next week's hunts are included even with an empty series."""
    window_start = week_start - timedelta(weeks=FAMILY_SERIES_WEEKS - 1)
    campaign_monday = monday_of(campaign.start_date) if campaign else None
    known = families_for_user(db, user_id)
    by_id = {f["family_id"]: f for f in known}
    out: List[Dict[str, Any]] = []
    for fam in known:
        series_all = weekly_best_e1rm_series(db, user_id, fam["exercise_ids"])
        series = [(w, v) for w, v in series_all if window_start <= w <= week_start]
        if not series:
            continue
        slope = weekly_slope(series)
        projection = (
            projected_e1rm(series[-1][1], slope, PROJECTION_DAYS)
            if slope is not None else None
        )
        in_campaign = [v for w, v in series_all if campaign_monday and w >= campaign_monday]
        out.append({
            "family_id": fam["family_id"],
            "display_name": fam["display_name"],
            "is_big_three": fam["is_big_three"],
            "increment_lb": _r1(fam["increment_lb"]),
            "weekly_best_e1rm": [[w.isoformat(), _r1(v)] for w, v in series],
            "slope_6w": _r2(slope),
            "projection_14d": _r1(projection),
            "best_e1rm_campaign": _r1(max(in_campaign)) if in_campaign else None,
        })
    present = {f["family_id"] for f in out}
    if extra_families:
        from app.models.exercise_family import ExerciseFamily

        missing = [f for f in dict.fromkeys(extra_families) if f and f not in present]
        if missing:
            rows = db.query(ExerciseFamily).filter(ExerciseFamily.id.in_(missing)).all()
            for row in sorted(rows, key=lambda r: r.display_name):
                fam = by_id.get(row.id)
                out.append({
                    "family_id": row.id,
                    "display_name": row.display_name,
                    "is_big_three": bool(row.is_big_three),
                    "increment_lb": _r1(fam["increment_lb"] if fam else row.increment_lb),
                    "weekly_best_e1rm": [],
                    "slope_6w": None,
                    "projection_14d": None,
                    "best_e1rm_campaign": None,
                })
    out.sort(key=lambda f: f["display_name"])
    return out


# ---------------------------------------------------------------------------
# Condition, load, wearable
# ---------------------------------------------------------------------------


def condition_section(db: Session, user_id: str, as_of: date, age: Optional[int]) -> Dict[str, Any]:
    payload = compute_condition(db, user_id, as_of, age)
    return {
        "score": payload["score"],
        "band": payload["band"],
        "inputs": [
            {"key": i["key"], "subscore": i["subscore"]}
            for i in payload["inputs"] if i.get("available")
        ],
        "muscles_cooling": [
            {"name": m.get("muscle") or m.get("name"), "hours_left": _r1(m.get("hours_remaining"))}
            for m in payload.get("muscles_cooling", []) if m.get("status") == "cooling"
        ],
    }


def load_section(db: Session, user_id: str, as_of: date) -> Optional[Dict[str, Any]]:
    """W2's ``get_load_state`` compressed to what the model needs.

    Cross-workstream lazy import (W2). Fallback: ``null``.
    """
    try:
        from app.services.training_load_service import get_load_state
    except ImportError:
        return None
    try:
        state = get_load_state(db, user_id, as_of)
    except Exception as exc:
        logger.warning("get_load_state failed for %s: %s", user_id, exc)
        return None
    if not state:
        return None
    return {
        "as_of": _iso(state.get("as_of")),
        "run_acwr": _r2(state.get("run_acwr")),
        "total_acwr": _r2(state.get("total_acwr")),
        "band": state.get("band"),
        "miles_7d": _r2(state.get("miles_7d")),
        "miles_plan_7d": _r2(state.get("miles_plan_7d")),
        "longest_run_7d": _r2(state.get("longest_run_7d")),
        "flags": list(state.get("flags") or []),
        "series": [
            [
                _iso(row.get("local_date")),
                _r1(row.get("run_load")),
                _r1(row.get("total_load")),
                _r2(row.get("miles")),
            ]
            for row in (state.get("series") or [])
        ],
    }


def wearable_section(db: Session, user_id: str, as_of: date) -> List[Dict[str, Any]]:
    return [
        {
            "local_date": row["local_date"],
            "sleep_hours": row["sleep_hours"],
            "hrv": row["hrv"],
            "resting_heart_rate": row["resting_heart_rate"],
            "recovery_score": row["recovery_score"],
        }
        for row in daily_activity_series(db, user_id, WEARABLE_DAYS, as_of=as_of)
    ]


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------


def goal_flags(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """W1's ``goal_service.goal_flags``. Lazy import; fallback ``[]``."""
    try:
        from app.services.goal_service import goal_flags as _flags
    except ImportError:
        return []
    try:
        return list(_flags(db, user_id) or [])
    except Exception as exc:
        logger.warning("goal_flags failed for %s: %s", user_id, exc)
        return []


def objectives_section(db: Session, user_id: str, week_start: date, week_end: date) -> Dict[str, Any]:
    goals = (
        db.query(Goal)
        .options(joinedload(Goal.exercise))
        .filter(Goal.user_id == user_id, Goal.status == GoalStatus.ACTIVE.value)
        .order_by(Goal.created_at.asc())
        .all()
    )
    flags_by_goal = {f.get("goal_id"): f for f in goal_flags(db, user_id)}
    goal_rows = []
    for g in goals:
        flag = flags_by_goal.get(g.id, {})
        exercise = g.exercise
        family = flag.get("family_id") or (exercise.family_id if exercise else None)
        goal_rows.append({
            "goal_id": g.id,
            "kind": g.kind,
            "family_id": family,
            "exercise": exercise.name if exercise else None,
            "target_weight": _r1(g.target_weight),
            "target_reps": g.target_reps,
            "target_miles": _r2(g.target_miles),
            "deadline": g.deadline.isoformat(),
            "deadline_extensions": g.deadline_extensions or 0,
            "pace_status": flag.get("pace_status"),
            "goal_behind": bool(flag.get("goal_behind", False)),
            "goal_ambitious": bool(flag.get("goal_ambitious", False)),
            "required_weekly_gain": _r2(flag.get("required_weekly_gain")),
            "actual_weekly_gain": _r2(flag.get("actual_weekly_gain")),
        })

    pace = []
    for report in _get_goal_progress_reports(db, user_id):
        pace.append({
            "goal_id": report.goal_id,
            "exercise": report.exercise_name,
            "target": f"{_num(report.target_weight)}x{report.target_reps}",
            "deadline": report.deadline,
            "status": report.status.value if hasattr(report.status, "value") else str(report.status),
            "progress_percent": _r1(report.progress_percent),
            "required_weekly_gain": _r2(report.required_weekly_gain),
            "actual_weekly_gain": _r2(report.actual_weekly_gain),
            "weeks_remaining": _r1(report.weeks_remaining),
        })

    prs = []
    for pr in _get_week_prs(db, user_id, week_start, week_end):
        prs.append({
            "exercise": pr.exercise_name,
            "type": pr.pr_type.value if hasattr(pr.pr_type, "value") else str(pr.pr_type),
            "weight_lb": _r1(pr.weight),
            "reps": pr.reps,
            "e1rm": _r1(pr.value),
            "date": pr.achieved_at[:10] if pr.achieved_at else None,
        })

    gates_open = [
        {
            "name": g.name,
            "rank": g.rank,
            "family_id": g.family_id,
            "target_weight": _r1(g.target_weight),
            "target_reps": g.target_reps,
            "expires": _iso(g.expires_at),
        }
        for g in get_live_gates(db, user_id)
    ]
    window_start = datetime.combine(week_start, time.min)
    window_end = datetime.combine(week_end, time.max)
    gates_closed = []
    for g in get_gate_history(db, user_id):
        stamp = g.cleared_at if g.status == GateStatus.CLEARED.value else g.expires_at
        stamp = ensure_utc(stamp).replace(tzinfo=None) if stamp else None
        if stamp is None or not (window_start <= stamp <= window_end):
            continue
        gates_closed.append({
            "name": g.name,
            "rank": g.rank,
            "status": g.status,
            "date": stamp.date().isoformat(),
            "xp": g.xp_awarded,
        })
    return {
        "goals": goal_rows,
        "pace": pace,
        "prs_week": prs,
        "gates_open": gates_open,
        "gates_closed_week": gates_closed,
    }


# ---------------------------------------------------------------------------
# Candidates, profile
# ---------------------------------------------------------------------------


def last_debrief_decisions(db: Session, user_id: str, week_start: date) -> List[Dict[str, Any]]:
    """The previous week's stored decisions, compact: op, params, decision."""
    prev = (
        db.query(CoachOutput)
        .filter(
            CoachOutput.user_id == user_id,
            CoachOutput.kind == CoachOutputKind.DEBRIEF.value,
            CoachOutput.for_date == week_start - timedelta(days=7),
        )
        .first()
    )
    if prev is None:
        return []
    decisions = prev.decisions or {}
    adjustments = {a["id"]: a for a in ((prev.validated or {}).get("adjustments") or [])}
    out = []
    for adj_id, record in decisions.items():
        adj = adjustments.get(adj_id, {})
        out.append({
            "op": adj.get("op") or record.get("op"),
            "params": adj.get("params") or record.get("params") or {},
            "decision": record.get("decision"),
        })
    return out


def candidates_section(db: Session, user_id: str, week_start: date) -> Dict[str, Any]:
    from app.services.debrief_service import build_candidates  # sibling module; avoid a cycle

    candidates = build_candidates(db, user_id, week_start)
    return {
        "adherence": candidates["adherence"],
        "highlights": candidates["highlights"],
        "concerns": candidates["concerns"],
        "candidate_ops": candidates["candidate_ops"],
        "last_debrief_decisions": last_debrief_decisions(db, user_id, week_start),
    }


def profile_section(db: Session, user_id: str, profile: Optional[UserProfile]) -> Dict[str, Any]:
    entries = (
        db.query(BodyweightEntry)
        .filter(BodyweightEntry.user_id == user_id)
        .order_by(desc(BodyweightEntry.date))
        .limit(2)
        .all()
    )
    trend = [
        {"date": e.date.isoformat(), "weight_lb": _r1(e.weight_lb)}
        for e in sorted(entries, key=lambda e: e.date)
    ]
    unit = profile.preferred_unit if profile else None
    return {
        "age": profile.age if profile else None,
        "sex": profile.sex if profile else None,
        "bodyweight_trend": trend,
        "injury_notes": profile.injury_notes if profile else None,
        "preferred_unit": getattr(unit, "value", unit) if unit else "lb",
    }


# ---------------------------------------------------------------------------
# Budget, hashing, entry point
# ---------------------------------------------------------------------------


def _canonical_json(ctx: Dict[str, Any]) -> str:
    return json.dumps(ctx, sort_keys=False, separators=(",", ":"), default=str)


def context_hash(ctx: Dict[str, Any]) -> str:
    """sha256 of the fixed-order compact JSON (spec §8.2)."""
    return hashlib.sha256(_canonical_json(ctx).encode("utf-8")).hexdigest()


def estimate_tokens(ctx: Dict[str, Any]) -> int:
    """Cheap token estimate: one token per four JSON characters."""
    return len(_canonical_json(ctx)) // 4 + 1


def _truncate_once(ctx: Dict[str, Any]) -> Optional[str]:
    """Drop the oldest slice of the biggest optional section; return its name."""
    sessions = ctx.get("sessions_4w") or []
    if len(sessions) > 1:
        ctx["sessions_4w"] = sessions[1:]
        return "sessions_4w"
    families = ctx.get("families") or []
    if any(len(f["weekly_best_e1rm"]) > 6 for f in families):
        for f in families:
            f["weekly_best_e1rm"] = f["weekly_best_e1rm"][-6:]
        return "families"
    load = ctx.get("load")
    if load and len(load.get("series") or []) > 14:
        load["series"] = load["series"][-14:]
        return "load"
    wearable = ctx.get("wearable_14d") or []
    if len(wearable) > 7:
        ctx["wearable_14d"] = wearable[-7:]
        return "wearable_14d"
    return None


def enforce_budget(ctx: Dict[str, Any], budget: int = TOKEN_BUDGET) -> Dict[str, Any]:
    """Truncate sections oldest-first until the estimate fits; record what
    was cut in ``ctx["truncated"]``."""
    truncated: List[str] = list(ctx.get("truncated") or [])
    while estimate_tokens(ctx) > budget:
        section = _truncate_once(ctx)
        if section is None:
            break
        if section not in truncated:
            truncated.append(section)
    ctx["truncated"] = truncated
    return ctx


def build_context(
    db: Session,
    user_id: str,
    week_start: date,
    *,
    client_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Compose the athlete context for the ISO week starting ``week_start``.

    ``client_date`` is the user's local day (Condition and the wearable
    window are anchored on it); it defaults to the week's Sunday.
    """
    week_start = monday_of(week_start)
    week_end = week_start + timedelta(days=6)
    as_of = client_date or week_end
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    campaign = active_campaign(db, user_id)

    campaign_ctx = campaign_section(db, user_id, week_start, campaign)
    next_families = [
        lift.get("family")
        for hunt in (campaign_ctx or {}).get("next_hunts", [])
        for lift in hunt.get("lifts", [])
    ]

    ctx: Dict[str, Any] = {
        "version": CONTEXT_VERSION,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "as_of": as_of.isoformat(),
        "campaign": campaign_ctx,
        "sessions_4w": sessions_section(db, user_id, week_start),
        "families": families_section(db, user_id, week_start, campaign, next_families),
        "condition_today": condition_section(db, user_id, as_of, profile.age if profile else None),
        "load": load_section(db, user_id, as_of),
        "wearable_14d": wearable_section(db, user_id, as_of),
        "objectives": objectives_section(db, user_id, week_start, week_end),
        "candidates": candidates_section(db, user_id, week_start),
        "profile": profile_section(db, user_id, profile),
        "truncated": [],
    }
    ordered = {key: ctx[key] for key in SECTION_ORDER}
    return enforce_budget(ordered)


__all__ = [
    "CONTEXT_VERSION",
    "SECTION_ORDER",
    "TOKEN_BUDGET",
    "active_campaign",
    "build_context",
    "context_hash",
    "enforce_budget",
    "estimate_tokens",
    "load_sessions",
    "monday_of",
    "planned_hunts_between",
    "session_local_day",
    "week_target_miles",
]
