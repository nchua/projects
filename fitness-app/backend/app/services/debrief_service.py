"""
The weekly Debrief (ARISE v3 spec §8.4–8.7).

Three steps, engine first:

1. **Engine** (``build_candidates``): adherence counts, highlights, concerns
   from the guard's flags / progression verdicts / Condition / sleep /
   objectives, and typed *candidate ops* with their numbers. The engine owns
   every number.
2. **Model** (``run_model``): ``client.beta.messages.parse`` with
   ``DebriefModelOutput``. The model writes prose, ranks the candidates to
   ≤ 3 and may add ops only from the typed vocabulary.
3. **Validators** (``validate_adjustments``): deterministic bounds on every
   op; out-of-bounds ops are kept, visible, and can never be accepted.

``get_or_create_debrief`` is lazy and idempotent per (user, week); on any
model failure the engine step alone is stored (``source: engine_fallback``).
The weekly-report push fires once, when a debrief is first stored.

Cross-workstream calls (W1 ``campaign_service`` / ``prescription_service`` /
``goal_service``, W2 ``training_load_service``) are imported lazily with a
documented neutral fallback so this module imports while those land.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from sqlalchemy.orm import Session, joinedload

from app.core.utils import ensure_utc, to_iso8601_utc
from app.models.campaign import Campaign, PlannedHunt, PlannedHuntStatus
from app.models.coach import CoachOutput, CoachOutputKind, CoachOutputSource
from app.models.gate import GateStatus, PRGate
from app.models.goal import Goal, GoalStatus
from app.models.pr import PR
from app.models.pr import PRType as PRTypeModel
from app.models.training_load import DailyTrainingLoad
from app.schemas.coach import (
    ADJUSTMENT_OPS,
    DebriefAdherence,
    DebriefAdjustment,
    DebriefConcern,
    DebriefHighlight,
    DebriefModelOutput,
    DebriefResponse,
)
from app.services import condition_service
from app.services.activity_series import daily_activity_series
from app.services.coach_context_service import (
    active_campaign,
    build_context,
    context_hash,
    estimate_tokens,
    load_sessions,
    monday_of,
    planned_hunts_between,
    run_miles,
    week_target_miles,
)
from app.services.notification_service import notify_weekly_report_ready
from app.services.weekly_report_service import _get_goal_progress_reports

logger = logging.getLogger(__name__)

PROMPT_VERSION = "debrief_v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "coach" / "prompts" / f"{PROMPT_VERSION}.md"
DEBRIEF_MODEL = "claude-opus-5"
# Spec §8.6 asks for ``fallbacks="default"`` + ``server-side-fallback-2026-07-01``;
# the pinned SDK (anthropic==0.111.0) only types the array form and the
# 2026-06-01 header, so that is what we send (see the W3 report).
FALLBACK_MODEL = "claude-opus-4-8"
FALLBACK_BETA = "server-side-fallback-2026-06-01"
MODEL_TIMEOUT_SECONDS = 60.0
MODEL_MAX_RETRIES = 1
MODEL_MAX_TOKENS = 8000
MODEL_EFFORT = "high"

MAX_ADJUSTMENTS = 3
MAX_CANDIDATES = 6
MAX_EXTEND_ARC_WEEKS = 2
MILES_TOLERANCE = 0.15
DEADLINE_MAX_EXTENSION_DAYS = 28
DELOAD_MIN_GAP_WEEKS = 3
CONDITION_LOW_THRESHOLD = 65
SLEEP_LOW_HOURS = 6.0
LOW_DAYS_THRESHOLD = 3
PLAN_DRIFT_MOVED = 2
ACWR_HIGH_FACTOR = 0.8
DEFAULT_DELOAD_FACTOR = 0.75
FOUR_WEEKS = 4

GUARD_FLAGS = ("ramp_high", "long_run_share", "run_acwr_high", "run_acwr_critical", "deload_due")
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
STATUS_PROPOSED = "proposed"
STATUS_ACCEPTED = "accepted"
STATUS_DISMISSED = "dismissed"
STATUS_OUT_OF_BOUNDS = "out_of_bounds"


class DebriefError(Exception):
    """Base for decision-flow errors the API maps to status codes."""


class AdjustmentNotFound(DebriefError):
    pass


class AdjustmentOutOfBounds(DebriefError):
    pass


class AdjustmentAlreadyDecided(DebriefError):
    pass


class ApplierUnavailable(DebriefError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _r1(value: Any) -> Optional[float]:
    return None if value is None else round(float(value), 1)


def _r2(value: Any) -> Optional[float]:
    return None if value is None else round(float(value), 2)


def _num(value: Any) -> Any:
    if value is None:
        return None
    rounded = round(float(value), 1)
    return int(rounded) if rounded == int(rounded) else rounded


def _pct(numerator: float, denominator: float) -> Optional[int]:
    if not denominator:
        return None
    return round((numerator / denominator - 1.0) * 100)


def default_week_start(today: date) -> date:
    """The most recent Monday whose week has ended by ``today`` — this
    week's on a Sunday, last week's on Monday–Saturday."""
    this_monday = monday_of(today)
    return this_monday if today.weekday() == 6 else this_monday - timedelta(days=7)


# ---------------------------------------------------------------------------
# Engine step
# ---------------------------------------------------------------------------


def adherence_counts(hunts: List[PlannedHunt]) -> Dict[str, int]:
    counts = {"planned": 0, "done": 0, "modified": 0, "moved": 0, "skipped": 0}
    for hunt in hunts:
        counts["planned"] += 1
        if hunt.status in counts:
            counts[hunt.status] += 1
    return counts


def _guard_snapshot(db: Session, user_id: str, as_of: date) -> Dict[str, Any]:
    """Guard flags + the numbers behind them on ``as_of``.

    W2's ``get_load_state`` / ``guard_flags_for_date`` (lazy). Fallback: the
    stored ``daily_training_load`` row for that day (W0 model, read-only).
    """
    snapshot: Dict[str, Any] = {
        "flags": [], "run_acwr": None, "miles_7d": None,
        "miles_plan_7d": None, "longest_run_7d": None,
    }
    try:
        from app.services.training_load_service import get_load_state, guard_flags_for_date
    except ImportError:
        row = (
            db.query(DailyTrainingLoad)
            .filter(DailyTrainingLoad.user_id == user_id, DailyTrainingLoad.local_date == as_of)
            .first()
        )
        if row is not None:
            snapshot.update({
                "flags": list(row.flags or []),
                "run_acwr": _r2(row.run_acwr),
                "miles_7d": _r2(row.miles_7d),
                "miles_plan_7d": _r2(row.miles_plan_7d),
                "longest_run_7d": _r2(row.longest_run_7d),
            })
        return snapshot
    try:
        state = get_load_state(db, user_id, as_of) or {}
        snapshot.update({
            "run_acwr": _r2(state.get("run_acwr")),
            "miles_7d": _r2(state.get("miles_7d")),
            "miles_plan_7d": _r2(state.get("miles_plan_7d")),
            "longest_run_7d": _r2(state.get("longest_run_7d")),
        })
        snapshot["flags"] = list(guard_flags_for_date(db, user_id, as_of) or state.get("flags") or [])
    except Exception as exc:
        logger.warning("load snapshot failed for %s: %s", user_id, exc)
    return snapshot


def _progression_verdicts(db: Session, user_id: str, week_start: date) -> List[Dict[str, Any]]:
    """W1's ``prescription_service.progression_verdicts``. Lazy; fallback ``[]``."""
    try:
        from app.services.prescription_service import progression_verdicts
    except ImportError:
        return []
    try:
        return list(progression_verdicts(db, user_id, week_start) or [])
    except Exception as exc:
        logger.warning("progression_verdicts failed for %s: %s", user_id, exc)
        return []


def _goal_flags(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """W1's ``goal_service.goal_flags``. Lazy; fallback ``[]``."""
    try:
        from app.services.goal_service import goal_flags
    except ImportError:
        return []
    try:
        return list(goal_flags(db, user_id) or [])
    except Exception as exc:
        logger.warning("goal_flags failed for %s: %s", user_id, exc)
        return []


# Past-day Condition approximation (spec §6.5 shape, cooldown input dropped).
# Self-contained on purpose: W2 owns ``condition_service`` and its private
# helpers change under it; only the public weight table is read, with a default.
_APPROX_WEIGHTS = {"recovery": 0.40, "sleep": 0.15, "strain_yesterday": 0.10, "rhr_trend": 0.10}
_APPROX_SLEEP_FLOOR_HOURS = 4.0
_APPROX_SLEEP_RANGE_HOURS = 3.5
_APPROX_STRAIN_NEUTRAL_MAX = 10.0
_APPROX_STRAIN_SCALE_MAX = 21.0
_APPROX_STRAIN_MIN_SUBSCORE = 40.0
_APPROX_RHR_POINTS_PER_BPM = 10.0
_APPROX_RHR_MIN_SUBSCORE = 40.0


def _approx_condition(
    row: Dict[str, Any], prev_row: Optional[Dict[str, Any]], rhr_baseline: Optional[float]
) -> Optional[int]:
    """Condition for a past day from the stored wearable series alone.

    ``compute_condition`` needs live cooldown state, which cannot be replayed
    for a past day, so this is the same weighted formula with the muscle
    freshness input dropped and the remaining weights renormalized (the
    service's own graceful-degradation rule). Returns None with no inputs.
    """
    weights = dict(_APPROX_WEIGHTS)
    for key, value in (getattr(condition_service, "CONDITION_WEIGHTS", None) or {}).items():
        if key in weights:
            weights[key] = float(value)
    inputs: Dict[str, Optional[float]] = {}
    recovery = row.get("recovery_score")
    inputs["recovery"] = None if recovery is None else max(0.0, min(100.0, float(recovery)))
    sleep = row.get("sleep_hours")
    if sleep is not None:
        frac = (float(sleep) - _APPROX_SLEEP_FLOOR_HOURS) / _APPROX_SLEEP_RANGE_HOURS
        inputs["sleep"] = max(0.0, min(1.0, frac)) * 100.0
    else:
        inputs["sleep"] = None
    strain = prev_row.get("strain") if prev_row else None
    if strain is None:
        inputs["strain_yesterday"] = None
    elif float(strain) <= _APPROX_STRAIN_NEUTRAL_MAX:
        inputs["strain_yesterday"] = 100.0
    else:
        fraction = (float(strain) - _APPROX_STRAIN_NEUTRAL_MAX) / (_APPROX_STRAIN_SCALE_MAX - _APPROX_STRAIN_NEUTRAL_MAX)
        inputs["strain_yesterday"] = max(
            _APPROX_STRAIN_MIN_SUBSCORE,
            min(100.0, 100.0 - fraction * (100.0 - _APPROX_STRAIN_MIN_SUBSCORE)),
        )
    rhr = row.get("resting_heart_rate")
    if rhr is not None and rhr_baseline is not None:
        penalty = _APPROX_RHR_POINTS_PER_BPM * max(0.0, float(rhr) - rhr_baseline)
        inputs["rhr_trend"] = max(_APPROX_RHR_MIN_SUBSCORE, min(100.0, 100.0 - penalty))
    else:
        inputs["rhr_trend"] = None
    available = sum(weights[k] for k, v in inputs.items() if v is not None)
    if available <= 0:
        return None
    total = sum(v * weights[k] for k, v in inputs.items() if v is not None)
    return round(total / available)


def _sleep_and_condition_concerns(db: Session, user_id: str, week_start: date, week_end: date) -> List[Dict[str, Any]]:
    series = daily_activity_series(db, user_id, 21, as_of=week_end)
    by_day = {row["local_date"]: row for row in series}
    week_days = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
    concerns: List[Dict[str, Any]] = []

    sleeps = [by_day[d]["sleep_hours"] for d in week_days if d in by_day and by_day[d]["sleep_hours"] is not None]
    low_nights = [s for s in sleeps if s < SLEEP_LOW_HOURS]
    if len(low_nights) >= LOW_DAYS_THRESHOLD:
        avg = _r1(sum(low_nights) / len(low_nights))
        concerns.append({
            "flag": "sleep_low",
            "text": f"Sleep under {_num(SLEEP_LOW_HOURS)} h on {len(low_nights)} nights (avg {avg} h).",
            "numbers": {"nights": len(low_nights), "avg_hours": avg},
        })

    baseline_rows = [r["resting_heart_rate"] for r in series[:-7] if r["resting_heart_rate"] is not None]
    rhr_baseline = sum(baseline_rows) / len(baseline_rows) if baseline_rows else None
    scores = []
    for day in week_days:
        row = by_day.get(day)
        if row is None:
            continue
        prev = by_day.get((date.fromisoformat(day) - timedelta(days=1)).isoformat())
        score = _approx_condition(row, prev, rhr_baseline)
        if score is not None:
            scores.append(score)
    low_days = [s for s in scores if s < CONDITION_LOW_THRESHOLD]
    if len(low_days) >= LOW_DAYS_THRESHOLD:
        concerns.append({
            "flag": "condition_low",
            "text": f"Condition under {CONDITION_LOW_THRESHOLD} on {len(low_days)} of 7 days (low {min(low_days)}).",
            "numbers": {"days": len(low_days), "min": min(low_days)},
        })
    return concerns


def _pr_highlights(db: Session, user_id: str, week_start: date, week_end: date) -> List[Dict[str, Any]]:
    start = datetime.combine(week_start, time.min)
    end = datetime.combine(week_end, time.max)
    prs = (
        db.query(PR)
        .options(joinedload(PR.exercise))
        .filter(PR.user_id == user_id, PR.achieved_at >= start, PR.achieved_at <= end)
        .order_by(PR.achieved_at.asc())
        .all()
    )
    out = []
    for pr in prs:
        name = pr.exercise.name if pr.exercise else "Unknown"
        if pr.pr_type == PRTypeModel.E1RM:
            prev = (
                db.query(PR.value)
                .filter(
                    PR.user_id == user_id,
                    PR.exercise_id == pr.exercise_id,
                    PR.pr_type == PRTypeModel.E1RM,
                    PR.achieved_at < pr.achieved_at,
                    PR.value.isnot(None),
                )
                .order_by(PR.value.desc())
                .first()
            )
            delta = _r1(pr.value - prev[0]) if prev and pr.value is not None else None
            lift = f"{_num(pr.weight)}×{pr.reps} → " if pr.weight and pr.reps else ""
            text = f"{name} {lift}e1RM {_num(pr.value)}"
            if delta is not None and delta > 0:
                text += f" (+{_num(delta)})"
            out.append({"kind": "pr", "text": text, "numbers": {"e1rm": _r1(pr.value), "delta": delta}})
        else:
            out.append({
                "kind": "pr",
                "text": f"{name} rep PR: {_num(pr.weight)}×{pr.reps}",
                "numbers": {"weight_lb": _r1(pr.weight), "reps": pr.reps},
            })
    return out


def _gate_highlights(db: Session, user_id: str, week_start: date, week_end: date) -> List[Dict[str, Any]]:
    start = datetime.combine(week_start, time.min)
    end = datetime.combine(week_end, time.max)
    gates = (
        db.query(PRGate)
        .filter(PRGate.user_id == user_id, PRGate.status == GateStatus.CLEARED.value)
        .all()
    )
    out = []
    for gate in gates:
        stamp = ensure_utc(gate.cleared_at).replace(tzinfo=None) if gate.cleared_at else None
        if stamp is None or not (start <= stamp <= end):
            continue
        xp = f" (+{gate.xp_awarded} XP)" if gate.xp_awarded else ""
        out.append({
            "kind": "gate_cleared",
            "text": f"{gate.name} cleared{xp}",
            "numbers": {"target_e1rm": _r1(gate.target_e1rm), "xp": gate.xp_awarded},
        })
    return out


def _run_highlights(db: Session, user_id: str, week_start: date, week_end: date, campaign: Optional[Campaign]) -> List[Dict[str, Any]]:
    if campaign is None:
        return []
    campaign_start = monday_of(campaign.start_date)
    if campaign_start > week_end:
        return []
    best_before = 0.0
    best_week: Optional[Tuple[float, date]] = None
    for day, session in load_sessions(db, user_id, campaign_start, week_end):
        miles = run_miles(session)
        if miles is None or not session.activity_type or "run" not in session.activity_type.lower():
            continue
        if day < week_start:
            best_before = max(best_before, miles)
        elif best_week is None or miles > best_week[0]:
            best_week = (miles, day)
    if best_week and best_week[0] > best_before and best_week[0] > 0:
        return [{
            "kind": "longest_run",
            "text": f"Longest run of the campaign: {best_week[0]} mi ({best_week[1].strftime('%a')})",
            "numbers": {"miles": best_week[0], "previous_best": _r2(best_before)},
        }]
    return []


def _on_plan_streak(db: Session, user_id: str, week_start: date) -> int:
    """Consecutive weeks ending at ``week_start`` with planned > 0 and no skips."""
    streak = 0
    cursor = week_start
    while True:
        hunts = planned_hunts_between(db, user_id, cursor, cursor + timedelta(days=6))
        counts = adherence_counts(hunts)
        if counts["planned"] == 0 or counts["skipped"] > 0:
            return streak
        streak += 1
        if streak >= 8:
            return streak
        cursor -= timedelta(days=7)


def _last_deload_gap_weeks(campaign: Optional[Campaign], week_start: date) -> Optional[int]:
    """Weeks between ``overrides['last_deload_week']`` and ``week_start``."""
    if campaign is None:
        return None
    last = (campaign.overrides or {}).get("last_deload_week")
    if not last:
        return None
    try:
        return (week_start - date.fromisoformat(last)).days // 7
    except ValueError:
        return None


def _deload_recent(campaign: Optional[Campaign], target_week: date) -> bool:
    gap = _last_deload_gap_weeks(campaign, target_week)
    return gap is not None and 0 <= gap < DELOAD_MIN_GAP_WEEKS


def _moved_pairs(hunts: List[PlannedHunt]) -> set:
    return {
        (h.date.weekday(), h.moved_to.weekday())
        for h in hunts
        if h.status == PlannedHuntStatus.MOVED.value and h.moved_to is not None
    }


def _candidate(op: str, reason: str, confidence: str, numbers: Dict[str, Any], **params: Any) -> Dict[str, Any]:
    return {"op": op, **params, "reason": reason, "confidence": confidence, "source": "engine", "numbers": numbers}


def build_candidates(db: Session, user_id: str, week_start: date) -> Dict[str, Any]:
    """Engine step (spec §8.4): adherence, highlights, concerns, candidate ops."""
    week_start = monday_of(week_start)
    week_end = week_start + timedelta(days=6)
    next_week = week_end + timedelta(days=1)
    campaign = active_campaign(db, user_id)
    hunts = planned_hunts_between(db, user_id, week_start, week_end)
    adherence = adherence_counts(hunts)

    # ── Highlights ────────────────────────────────────────────────────
    highlights: List[Dict[str, Any]] = []
    highlights += _pr_highlights(db, user_id, week_start, week_end)
    highlights += _gate_highlights(db, user_id, week_start, week_end)
    if adherence["planned"] > 0 and adherence["skipped"] == 0:
        highlights.append({
            "kind": "week_completed_as_planned",
            "text": f"Week completed as planned: {adherence['done'] + adherence['modified'] + adherence['moved']}/{adherence['planned']} hunts.",
            "numbers": dict(adherence),
        })
    highlights += _run_highlights(db, user_id, week_start, week_end, campaign)
    if _on_plan_streak(db, user_id, week_start) == FOUR_WEEKS:
        highlights.append({
            "kind": "four_weeks_on_plan",
            "text": "Four consecutive weeks on plan.",
            "numbers": {"weeks": FOUR_WEEKS},
        })

    # ── Concerns ──────────────────────────────────────────────────────
    concerns: List[Dict[str, Any]] = []
    guard = _guard_snapshot(db, user_id, week_end)
    flags = set(guard["flags"])
    miles_7d, plan_7d = guard["miles_7d"], guard["miles_plan_7d"]
    if "ramp_high" in flags:
        over = _pct(miles_7d or 0.0, plan_7d or 0.0)
        concerns.append({
            "flag": "ramp_high",
            "text": f"Ran {miles_7d} mi against {plan_7d} planned" + (f" (+{over}%)." if over is not None else "."),
            "numbers": {"miles_7d": miles_7d, "miles_plan_7d": plan_7d, "over_pct": over},
        })
    if "long_run_share" in flags:
        share = round((guard["longest_run_7d"] or 0.0) / miles_7d * 100) if miles_7d else None
        concerns.append({
            "flag": "long_run_share",
            "text": f"Longest run {guard['longest_run_7d']} mi is {share}% of the week's {miles_7d} mi.",
            "numbers": {"longest_run_7d": guard["longest_run_7d"], "miles_7d": miles_7d, "share_pct": share},
        })
    if "run_acwr_critical" in flags:
        concerns.append({
            "flag": "run_acwr_critical",
            "text": f"Run ACWR {guard['run_acwr']} (critical above 1.50).",
            "numbers": {"run_acwr": guard["run_acwr"]},
        })
    elif "run_acwr_high" in flags:
        concerns.append({
            "flag": "run_acwr_high",
            "text": f"Run ACWR {guard['run_acwr']} (limit 1.30).",
            "numbers": {"run_acwr": guard["run_acwr"]},
        })

    verdicts = _progression_verdicts(db, user_id, week_start)
    stalls = [v for v in verdicts if v.get("verdict") == "deload_lift"]
    if "deload_due" in flags:
        why = "two lifts stalled this week" if len(stalls) >= 2 else "the arc's cadence"
        concerns.append({
            "flag": "deload_due",
            "text": f"Deload due: {why}.",
            "numbers": {"stalled_lifts": len(stalls)},
        })
    for v in stalls:
        name = v.get("display_name") or v.get("family_id")
        held = v.get("last_weight_lb")
        concerns.append({
            "flag": "lift_stall",
            "text": f"{name}: {v.get('reason') or 'stalled'}" + (f" — held at {_num(held)} lb." if held is not None else "."),
            "numbers": {
                "family_id": v.get("family_id"),
                "last_weight_lb": _r1(held),
                "sets_hit": v.get("sets_hit"),
                "sets_total": v.get("sets_total"),
            },
        })

    concerns += _sleep_and_condition_concerns(db, user_id, week_start, week_end)

    goal_flags = _goal_flags(db, user_id)
    for flag in goal_flags:
        label = flag.get("family_id") or flag.get("exercise_id") or "objective"
        numbers = {
            "goal_id": flag.get("goal_id"),
            "family_id": flag.get("family_id"),
            "required_weekly_gain": _r2(flag.get("required_weekly_gain")),
            "actual_weekly_gain": _r2(flag.get("actual_weekly_gain")),
        }
        if flag.get("goal_behind"):
            concerns.append({
                "flag": "goal_behind",
                "text": f"{label} objective behind: needs +{numbers['required_weekly_gain']} lb/wk, actual +{numbers['actual_weekly_gain']}.",
                "numbers": numbers,
            })
        if flag.get("goal_ambitious"):
            concerns.append({
                "flag": "goal_ambitious",
                "text": f"{label} objective ambitious: needs +{numbers['required_weekly_gain']} lb/wk against a +{numbers['actual_weekly_gain']} slope.",
                "numbers": numbers,
            })

    if adherence["moved"] >= PLAN_DRIFT_MOVED:
        concerns.append({
            "flag": "plan_drift",
            "text": f"{adherence['moved']} hunts moved this week.",
            "numbers": {"moved": adherence["moved"]},
        })

    # ── Candidate ops ─────────────────────────────────────────────────
    ops: List[Dict[str, Any]] = []
    deload_recent = _deload_recent(campaign, next_week)
    deload_proposed = False
    if "deload_due" in flags and not deload_recent:
        scope = "all" if stalls else "runs"
        ops.append(_candidate(
            "deload_now", f"Deload due ({'two lifts stalled' if len(stalls) >= 2 else 'arc cadence'}); none in the last {DELOAD_MIN_GAP_WEEKS} weeks.",
            "high", {"stalled_lifts": len(stalls), "last_deload_week": (campaign.overrides or {}).get("last_deload_week") if campaign else None},
            scope=scope,
        ))
        deload_proposed = True

    arc_factor = DEFAULT_DELOAD_FACTOR
    if campaign is not None and campaign.arcs:
        from app.services.coach_context_service import arc_for_week

        arc, _, _ = arc_for_week(campaign, next_week)
        if arc is not None and arc.deload_factor:
            arc_factor = float(arc.deload_factor)
    next_target = week_target_miles(db, campaign, next_week)
    if next_target is not None:
        miles_op: Optional[Tuple[float, str, str]] = None
        if "deload_due" in flags:
            miles_op = (_r2(next_target * arc_factor), f"Deload week: {next_target} × {arc_factor}.", "high")
        elif "run_acwr_critical" in flags or "run_acwr_high" in flags:
            miles_op = (_r2(next_target * ACWR_HIGH_FACTOR), f"Run ACWR {guard['run_acwr']}: next week's {next_target} mi × {ACWR_HIGH_FACTOR}.", "high")
        elif "ramp_high" in flags and plan_7d:
            miles_op = (_r2(plan_7d), f"Ahead of the ramp ({miles_7d} vs {plan_7d} planned): hold next week at {plan_7d} mi instead of {next_target}.", "high")
        if miles_op is not None:
            ops.append(_candidate(
                "set_week_miles", miles_op[1], miles_op[2],
                {"plan_next_week": next_target, "miles_7d": miles_7d, "miles_plan_7d": plan_7d, "run_acwr": guard["run_acwr"]},
                week_start=next_week.isoformat(), miles=miles_op[0],
            ))

    for v in stalls:
        family = v.get("family_id")
        if not family:
            continue
        if not deload_recent and not deload_proposed:
            ops.append(_candidate(
                "deload_now", f"{v.get('display_name') or family} stalled ({v.get('reason') or 'sets missed'}); no deload in the last {DELOAD_MIN_GAP_WEEKS} weeks.",
                "medium", {"family_id": family, "last_weight_lb": _r1(v.get("last_weight_lb"))},
                scope="lifts",
            ))
            deload_proposed = True
        else:
            increment = v.get("increment_lb")
            if increment is None:
                continue
            ops.append(_candidate(
                "set_progression", f"{v.get('display_name') or family} stalled at {_num(v.get('last_weight_lb'))} lb with a deload already used; re-anchor progression at +{_num(increment)} lb.",
                "medium", {"family_id": family, "last_weight_lb": _r1(v.get("last_weight_lb")), "increment_lb": _r1(increment)},
                family=family, increment_lb=float(increment),
            ))

    behind = [f for f in goal_flags if f.get("goal_behind")]
    for flag in behind:
        family = flag.get("family_id")
        target_reps = flag.get("target_reps") or 1
        if family:
            reps = max(3, min(int(target_reps), 5))
            ops.append(_candidate(
                "change_reps", f"Objective behind (needs +{_r2(flag.get('required_weekly_gain'))} lb/wk, actual +{_r2(flag.get('actual_weekly_gain'))}); shift {family} to 3×{reps} toward the {target_reps}-rep target.",
                "medium", {"goal_id": flag.get("goal_id"), "required_weekly_gain": _r2(flag.get("required_weekly_gain")), "actual_weekly_gain": _r2(flag.get("actual_weekly_gain"))},
                family=family, sets=3, reps=[reps, reps],
            ))
        goal = db.query(Goal).filter(Goal.id == flag.get("goal_id"), Goal.user_id == user_id).first()
        if goal is not None and (goal.deadline_extensions or 0) == 0 and goal.status == GoalStatus.ACTIVE.value:
            new_deadline = goal.deadline + timedelta(days=DEADLINE_MAX_EXTENSION_DAYS)
            ops.append(_candidate(
                "set_goal_deadline", f"Objective behind at +{_r2(flag.get('actual_weekly_gain'))} lb/wk against +{_r2(flag.get('required_weekly_gain'))} needed; extend the deadline {DEADLINE_MAX_EXTENSION_DAYS // 7} weeks to {new_deadline.isoformat()}.",
                "medium", {"goal_id": goal.id, "deadline": goal.deadline.isoformat(), "deadline_extensions": goal.deadline_extensions or 0},
                goal_id=goal.id, deadline=new_deadline.isoformat(),
            ))

    if adherence["moved"] > 0:
        prev_hunts = planned_hunts_between(db, user_id, week_start - timedelta(days=7), week_start - timedelta(days=1))
        repeated = sorted(_moved_pairs(hunts) & _moved_pairs(prev_hunts))
        if repeated:
            src, dst = repeated[0]
            a = next_week + timedelta(days=src)
            b = next_week + timedelta(days=dst)
            ops.append(_candidate(
                "swap_days", f"{a.strftime('%A')} moved to {b.strftime('%A')} two weeks running; swap them in the plan.",
                "low", {"from_weekday": src, "to_weekday": dst, "weeks": 2},
                a=a.isoformat(), b=b.isoformat(),
            ))

    return {
        "adherence": adherence,
        "highlights": highlights,
        "concerns": concerns,
        "candidate_ops": ops[:MAX_CANDIDATES],
    }


def describe_op(op: Dict[str, Any]) -> str:
    """One terse clause naming the op and its numbers (engine copy)."""
    kind = op.get("op")
    params = op.get("params") or {k: v for k, v in op.items() if k not in ("op", "reason", "confidence", "source", "numbers", "status", "id", "validation_note")}
    if kind == "set_progression":
        return f"{params.get('family')} +{_num(params.get('increment_lb'))} lb"
    if kind == "set_week_miles":
        return f"{_num(params.get('miles'))} mi for the week of {params.get('week_start')}"
    if kind == "deload_now":
        return f"deload {params.get('scope')}"
    if kind == "swap_days":
        return f"swap {params.get('a')} and {params.get('b')}"
    if kind == "extend_arc":
        return f"extend the arc {params.get('weeks')} week(s)"
    if kind == "change_reps":
        reps = params.get("reps") or []
        rep_text = f"{reps[0]}" if reps and len(set(reps)) == 1 else "-".join(str(r) for r in reps)
        return f"{params.get('family')} {params.get('sets')}×{rep_text}"
    if kind == "set_goal_deadline":
        return f"objective deadline → {params.get('deadline')}"
    return str(kind)


def engine_summary(candidates: Dict[str, Any]) -> str:
    """Fallback summary: adherence, top concern, top op (≤ 3 sentences)."""
    a = candidates.get("adherence") or {}
    if a.get("planned", 0) == 0:
        first = "No planned hunts this week."
    else:
        parts = [f"{a.get('done', 0)} of {a['planned']} hunts done"]
        for key in ("modified", "moved", "skipped"):
            if a.get(key):
                parts.append(f"{a[key]} {key}")
        first = ", ".join(parts) + "."
    concerns = candidates.get("concerns") or []
    second = f"Top concern: {concerns[0]['text']}" if concerns else "No flags raised."
    if not second.endswith("."):
        second += "."
    ops = candidates.get("candidate_ops") or []
    third = f"Proposed: {describe_op(ops[0])}." if ops else "No adjustment proposed; the plan stands."
    return " ".join((first, second, third))


# ---------------------------------------------------------------------------
# Model step
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_anthropic_client() -> anthropic.Anthropic:
    """Per-call client from ``ANTHROPIC_API_KEY`` (spec §8.6): explicit
    timeout, one retry. Monkeypatched in tests."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(
        api_key=api_key, timeout=MODEL_TIMEOUT_SECONDS, max_retries=MODEL_MAX_RETRIES
    )


def system_blocks() -> List[Dict[str, Any]]:
    """Frozen prompt + schema first with ``cache_control`` (§8.6 caching)."""
    schema = json.dumps(DebriefModelOutput.model_json_schema(), separators=(",", ":"))
    return [{
        "type": "text",
        "text": f"{load_prompt()}\n\n## Output schema (JSON Schema)\n\n{schema}\n",
        "cache_control": {"type": "ephemeral"},
    }]


def run_model(ctx: Dict[str, Any]) -> Tuple[Optional[DebriefModelOutput], Optional[Dict[str, Any]], Optional[str]]:
    """One structured-output call. Returns ``(parsed, raw_json, failure)``;
    ``failure`` is set (and ``parsed`` None) on timeout, API error, refusal
    or a schema failure — the caller falls back to the engine step."""
    user_content = json.dumps(ctx, separators=(",", ":"), default=str)
    try:
        client = build_anthropic_client()
        response = client.beta.messages.parse(
            model=DEBRIEF_MODEL,
            max_tokens=MODEL_MAX_TOKENS,
            system=system_blocks(),
            messages=[{"role": "user", "content": user_content}],
            output_format=DebriefModelOutput,
            output_config={"effort": MODEL_EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks=[{"model": FALLBACK_MODEL}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "debrief model usage: input=%s output=%s cache_read=%s cache_write=%s model=%s",
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
                getattr(usage, "cache_read_input_tokens", None),
                getattr(usage, "cache_creation_input_tokens", None),
                getattr(response, "model", DEBRIEF_MODEL),
            )
        if getattr(response, "stop_reason", None) == "refusal":
            logger.warning("debrief model refused (stop_details=%s)", getattr(response, "stop_details", None))
            return None, None, "refusal"
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            return None, None, "no_parsed_output"
        if not isinstance(parsed, DebriefModelOutput):
            parsed = DebriefModelOutput.model_validate(parsed)
        return parsed, parsed.model_dump(mode="json"), None
    except anthropic.APITimeoutError:
        logger.error("debrief model timeout after %ss", MODEL_TIMEOUT_SECONDS)
        return None, None, "timeout"
    except anthropic.APIError as exc:
        logger.error("debrief model API error: %s", exc)
        return None, None, "api_error"
    except Exception as exc:  # pydantic ValidationError, missing key, anything else
        logger.error("debrief model failed: %s: %s", type(exc).__name__, exc)
        return None, None, "schema"


# ---------------------------------------------------------------------------
# Validators (deterministic, context-driven)
# ---------------------------------------------------------------------------


def _split_params(adj: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: v for k, v in adj.items()
        if k not in ("op", "reason", "confidence", "source", "numbers", "id", "status", "validation_note", "params")
    }


def _ctx_families(ctx: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {f["family_id"]: f for f in (ctx.get("families") or [])}


def _ctx_goals(ctx: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {g["goal_id"]: g for g in ((ctx.get("objectives") or {}).get("goals") or [])}


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def validate_one(ctx: Dict[str, Any], adj: Dict[str, Any], *, has_deload: bool) -> Optional[str]:
    """Return a validation note when ``adj`` is out of bounds, else None."""
    op = adj.get("op")
    p = adj.get("params") or {}
    families = _ctx_families(ctx)
    campaign = ctx.get("campaign") or {}
    week_start = _parse_date(ctx.get("week_start"))
    next_week = week_start + timedelta(days=7) if week_start else None

    if op not in ADJUSTMENT_OPS:
        return f"Unknown op {op!r}."

    if op in ("set_progression", "change_reps"):
        family = p.get("family")
        if family not in families:
            return f"Unknown family {family!r}; must be one of the families in the context."

    if op == "set_progression":
        expected = families[p["family"]].get("increment_lb")
        given = p.get("increment_lb")
        if expected is None or given is None or abs(float(given) - float(expected)) > 1e-6:
            return f"increment_lb must equal the family's {_num(expected)} lb (got {_num(given)})."
        return None

    if op == "set_week_miles":
        target_week = _parse_date(p.get("week_start"))
        miles = p.get("miles")
        if target_week is None or miles is None or float(miles) <= 0:
            return "set_week_miles needs a week_start and miles above zero."
        if target_week == next_week:
            plan = campaign.get("next_week_target_miles")
        elif target_week == week_start:
            plan = campaign.get("week_target_miles")
        else:
            plan = None
        if plan is None:
            return f"No arc target for the week of {target_week.isoformat()}."
        if has_deload or _matches_engine_candidate(ctx, adj):
            return None
        lo, hi = plan * (1 - MILES_TOLERANCE), plan * (1 + MILES_TOLERANCE)
        if not (lo <= float(miles) <= hi):
            return f"{_num(miles)} mi is outside ±{int(MILES_TOLERANCE * 100)}% of the arc's {_num(plan)} mi ({_num(_r2(lo))}–{_num(_r2(hi))})."
        return None

    if op == "deload_now":
        if p.get("scope") not in ("lifts", "runs", "all"):
            return "deload_now scope must be lifts, runs or all."
        last = _parse_date(campaign.get("last_deload_week"))
        if last is not None and next_week is not None:
            gap = (next_week - last).days // 7
            if 0 <= gap < DELOAD_MIN_GAP_WEEKS:
                return f"One deload per {DELOAD_MIN_GAP_WEEKS} weeks; the last was the week of {last.isoformat()}."
        return None

    if op == "swap_days":
        a, b = _parse_date(p.get("a")), _parse_date(p.get("b"))
        if a is None or b is None or a == b:
            return "swap_days needs two different dates."
        if next_week is None or not (next_week <= a <= next_week + timedelta(days=6) and next_week <= b <= next_week + timedelta(days=6)):
            return "swap_days dates must both fall in next week."
        planned = {h.get("date") for h in campaign.get("next_hunts") or []}
        if a.isoformat() not in planned or b.isoformat() not in planned:
            return "Both swap_days dates must carry a planned hunt."
        return None

    if op == "extend_arc":
        weeks = p.get("weeks")
        if not isinstance(weeks, int) or not (1 <= weeks <= MAX_EXTEND_ARC_WEEKS):
            return f"extend_arc must be 1–{MAX_EXTEND_ARC_WEEKS} weeks (got {weeks})."
        return None

    if op == "change_reps":
        sets, reps = p.get("sets"), p.get("reps")
        if not isinstance(sets, int) or not (1 <= sets <= 10):
            return "change_reps sets must be 1–10."
        if not isinstance(reps, list) or not reps or any((not isinstance(r, int)) or r < 1 or r > 30 for r in reps):
            return "change_reps reps must be a [lo, hi] list of 1–30."
        return None

    if op == "set_goal_deadline":
        goal = _ctx_goals(ctx).get(p.get("goal_id"))
        if goal is None:
            return "Unknown objective."
        if (goal.get("deadline_extensions") or 0) > 0:
            return "This objective's deadline was already extended once."
        current = _parse_date(goal.get("deadline"))
        new = _parse_date(p.get("deadline"))
        if current is None or new is None or new <= current:
            return "set_goal_deadline must extend the deadline."
        if (new - current).days > DEADLINE_MAX_EXTENSION_DAYS:
            return f"Extend by at most {DEADLINE_MAX_EXTENSION_DAYS // 7} weeks ({(new - current).days} days requested)."
        return None

    return None


def _matches_engine_candidate(ctx: Dict[str, Any], adj: Dict[str, Any]) -> bool:
    """True when the op repeats an engine candidate number-for-number. The
    guard's reductions (e.g. ACWR × 0.8) are the engine's own numbers, so
    they are in bounds by construction even outside the ±15% band."""
    p = adj.get("params") or {}
    for cand in (ctx.get("candidates") or {}).get("candidate_ops") or []:
        if cand.get("op") != adj.get("op"):
            continue
        cand_params = _split_params(cand)
        if all(cand_params.get(k) == p.get(k) for k in cand_params):
            return True
    return False


def _normalize_confidence(value: Any) -> str:
    return value if value in CONFIDENCE_RANK else "medium"


def validate_adjustments(ctx: Dict[str, Any], adjustments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn raw ops (model output or engine candidates) into stored
    adjustments with ids and a status; cap at ``MAX_ADJUSTMENTS`` dropping
    the lowest confidence first."""
    prepared = []
    for raw in adjustments:
        op = raw.get("op")
        prepared.append({
            "id": raw.get("id") or str(uuid.uuid4()),
            "op": op,
            "params": raw.get("params") if isinstance(raw.get("params"), dict) else _split_params(raw),
            "reason": raw.get("reason") or "",
            "confidence": _normalize_confidence(raw.get("confidence")),
            "source": raw.get("source") if raw.get("source") in ("engine", "model") else "model",
        })
    ranked = sorted(prepared, key=lambda a: -CONFIDENCE_RANK[a["confidence"]])
    kept = ranked[:MAX_ADJUSTMENTS]
    has_deload = any(a["op"] == "deload_now" and a["params"].get("scope") in ("runs", "all") for a in kept)
    out = []
    for adj in kept:
        note = validate_one(ctx, adj, has_deload=has_deload)
        adj["status"] = STATUS_OUT_OF_BOUNDS if note else STATUS_PROPOSED
        adj["validation_note"] = note
        out.append(adj)
    return out


def normalize_concerns(ctx: Dict[str, Any], model_concerns: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """The model's text with the engine's flags: any flag the engine did not
    raise becomes ``other``; engine concerns the model skipped are kept."""
    engine = (ctx.get("candidates") or {}).get("concerns") or []
    raised = [c["flag"] for c in engine]
    out: List[Dict[str, str]] = []
    seen = set()
    for c in model_concerns:
        flag = c.get("flag") if c.get("flag") in raised else "other"
        text = (c.get("text") or "").strip()
        if not text:
            continue
        out.append({"flag": flag, "text": text})
        seen.add(flag)
    for c in engine:
        if c["flag"] not in seen:
            out.append({"flag": c["flag"], "text": c["text"]})
    return out


# ---------------------------------------------------------------------------
# Assembly, storage, orchestration
# ---------------------------------------------------------------------------


def _fallback_focus(candidates: Dict[str, Any], adjustments: List[Dict[str, Any]]) -> str:
    proposed = [a for a in adjustments if a["status"] == STATUS_PROPOSED]
    if proposed:
        return f"Decide on {describe_op(proposed[0])}."
    concerns = candidates.get("concerns") or []
    if concerns:
        return f"Address {concerns[0]['flag']}."
    return "Run the plan as written."


def assemble_validated(
    ctx: Dict[str, Any],
    parsed: Optional[DebriefModelOutput],
) -> Dict[str, Any]:
    """The stored ``validated`` JSON. Adherence, highlights and every number
    come from the engine regardless of what the model wrote."""
    candidates = ctx.get("candidates") or {}
    highlights = [{"kind": h["kind"], "text": h["text"]} for h in candidates.get("highlights") or []]
    engine_line = engine_summary(candidates)
    if parsed is not None:
        adjustments = validate_adjustments(ctx, [a.model_dump(mode="json") for a in parsed.adjustments])
        concerns = normalize_concerns(ctx, [c.model_dump() for c in parsed.concerns])
        summary = parsed.summary.strip() or engine_line
        focus = parsed.next_week_focus.strip() or _fallback_focus(candidates, adjustments)
    else:
        adjustments = validate_adjustments(ctx, list(candidates.get("candidate_ops") or []))
        concerns = [{"flag": c["flag"], "text": c["text"]} for c in candidates.get("concerns") or []]
        summary = engine_line
        focus = _fallback_focus(candidates, adjustments)
    return {
        "summary": summary,
        "next_week_focus": focus,
        "adherence": dict(candidates.get("adherence") or {}),
        "highlights": highlights,
        "concerns": concerns,
        "adjustments": adjustments,
        "candidate_ops": list(candidates.get("candidate_ops") or []),
        "engine_summary": engine_line,
        "context_tokens": estimate_tokens(ctx),
    }


def _saturday_linked(db: Session, user_id: str, week_start: date) -> bool:
    saturday = week_start + timedelta(days=5)
    return (
        db.query(PlannedHunt.id)
        .filter(
            PlannedHunt.user_id == user_id,
            PlannedHunt.date == saturday,
            PlannedHunt.session_id.isnot(None),
        )
        .first()
    ) is not None


def generation_allowed(db: Session, user_id: str, week_start: date, today: date) -> bool:
    """Spec §8.4: after Sunday (the hour is not known server-side, so any
    time on Sunday counts), or on demand once Saturday's hunt is linked."""
    if today >= week_start + timedelta(days=6):
        return True
    return today >= week_start + timedelta(days=5) and _saturday_linked(db, user_id, week_start)


def _fire_weekly_report_push(db: Session, user_id: str) -> None:
    """Fire-and-forget the weekly-report push (moved here from
    ``api/weekly_report.py``): scheduled on the running loop when there is
    one, run to completion otherwise."""
    try:
        result = notify_weekly_report_ready(db, user_id)
        if not inspect.isawaitable(result):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            loop.create_task(result)
        else:
            asyncio.run(result)
    except Exception as exc:  # never let a push failure break the debrief
        logger.warning("weekly report push failed for %s: %s", user_id, exc)


def _get_existing(db: Session, user_id: str, week_start: date) -> Optional[CoachOutput]:
    return (
        db.query(CoachOutput)
        .filter(
            CoachOutput.user_id == user_id,
            CoachOutput.kind == CoachOutputKind.DEBRIEF.value,
            CoachOutput.for_date == week_start,
        )
        .first()
    )


def get_or_create_debrief(
    db: Session,
    user_id: str,
    week_start: date,
    *,
    client_date: Optional[date] = None,
    force: bool = False,
) -> CoachOutput:
    """Lazy, idempotent per (user, week). Before the week has ended the
    engine-only fallback is returned without being stored (unless ``force``).
    The weekly-report push fires once, when a row is first stored."""
    week_start = monday_of(week_start)
    existing = _get_existing(db, user_id, week_start)
    if existing is not None and not force:
        return existing

    ctx = build_context(db, user_id, week_start, client_date=client_date)
    digest = context_hash(ctx)
    today = client_date or date.today()

    if not force and not generation_allowed(db, user_id, week_start, today):
        preview = CoachOutput(
            id=f"preview-{uuid.uuid4()}",
            user_id=user_id,
            kind=CoachOutputKind.DEBRIEF.value,
            for_date=week_start,
            context_hash=digest,
            prompt_version=PROMPT_VERSION,
            model=DEBRIEF_MODEL,
            output=None,
            validated=assemble_validated(ctx, None),
            decisions={},
            source=CoachOutputSource.ENGINE_FALLBACK.value,
            created_at=datetime.now(timezone.utc),
        )
        return preview

    parsed, raw, failure = run_model(ctx)
    validated = assemble_validated(ctx, parsed)
    if parsed is None:
        validated["fallback_reason"] = failure

    row = existing or CoachOutput(
        user_id=user_id,
        kind=CoachOutputKind.DEBRIEF.value,
        for_date=week_start,
    )
    is_new = existing is None
    row.context_hash = digest
    row.prompt_version = PROMPT_VERSION
    row.model = DEBRIEF_MODEL
    row.output = raw if parsed is not None else {"failure": failure}
    row.validated = validated
    row.decisions = {}
    row.source = (
        CoachOutputSource.MODEL.value if parsed is not None
        else CoachOutputSource.ENGINE_FALLBACK.value
    )
    if is_new:
        db.add(row)
    db.commit()
    db.refresh(row)
    if is_new:
        _fire_weekly_report_push(db, user_id)
    return row


def debrief_to_response(db: Session, row: CoachOutput, user_id: str) -> DebriefResponse:
    validated = row.validated or {}
    adherence = validated.get("adherence") or {}
    return DebriefResponse(
        id=row.id,
        week_start=row.for_date.isoformat(),
        summary=validated.get("summary") or "",
        adherence=DebriefAdherence(
            planned=adherence.get("planned", 0),
            done=adherence.get("done", 0),
            modified=adherence.get("modified", 0),
            moved=adherence.get("moved", 0),
            skipped=adherence.get("skipped", 0),
        ),
        highlights=[DebriefHighlight(**h) for h in validated.get("highlights") or []],
        concerns=[DebriefConcern(**c) for c in validated.get("concerns") or []],
        adjustments=[
            DebriefAdjustment(
                id=a["id"],
                op=a["op"],
                params=a.get("params") or {},
                reason=a.get("reason") or "",
                confidence=a.get("confidence") or "medium",
                source=a.get("source") or "engine",
                status=a.get("status") or STATUS_PROPOSED,
                validation_note=a.get("validation_note"),
            )
            for a in validated.get("adjustments") or []
        ],
        next_week_focus=validated.get("next_week_focus") or "",
        goal_reports=_get_goal_progress_reports(db, user_id),
        generated_at=to_iso8601_utc(ensure_utc(row.created_at)) or "",
        source=row.source,
    )


# ---------------------------------------------------------------------------
# Decisions (accept / dismiss)
# ---------------------------------------------------------------------------


def _apply_adjustment(db: Session, user_id: str, week_start: date, adj: Dict[str, Any]) -> List[str]:
    """Route an accepted op to W1's appliers. Cross-workstream lazy imports;
    ``ImportError`` → ``ApplierUnavailable`` (503), ``ValueError`` → 422."""
    op, p = adj["op"], adj.get("params") or {}
    next_week = week_start + timedelta(days=7)
    if op == "set_goal_deadline":
        try:
            from app.services.goal_service import extend_goal_deadline
        except ImportError as exc:
            raise ApplierUnavailable("Objective appliers are not available yet.") from exc
        goal = extend_goal_deadline(db, user_id, p["goal_id"], date.fromisoformat(p["deadline"]))
        return [goal.id]

    try:
        cs = importlib.import_module("app.services.campaign_service")
    except ImportError as exc:
        raise ApplierUnavailable("Campaign appliers are not available yet.") from exc
    campaign = cs.get_active_campaign(db, user_id)
    if campaign is None:
        raise ValueError("No active campaign to apply this adjustment to.")
    if op == "set_progression":
        return list(cs.apply_set_progression(db, campaign, p["family"], float(p["increment_lb"])))
    if op == "set_week_miles":
        return list(cs.apply_set_week_miles(db, campaign, date.fromisoformat(p["week_start"]), float(p["miles"])))
    if op == "deload_now":
        return list(cs.apply_deload_now(db, campaign, next_week, p["scope"]))
    if op == "swap_days":
        return list(cs.apply_swap_days(db, campaign, date.fromisoformat(p["a"]), date.fromisoformat(p["b"])))
    if op == "extend_arc":
        return list(cs.apply_extend_arc(db, campaign, int(p["weeks"])))
    if op == "change_reps":
        return list(cs.apply_change_reps(db, campaign, p["family"], int(p["sets"]), [int(r) for r in p["reps"]]))
    raise ValueError(f"Unknown op {op!r}.")


def apply_decision(db: Session, row: CoachOutput, adj_id: str, decision: str) -> CoachOutput:
    """Accept (apply via W1) or dismiss one adjustment; record it in
    ``decisions`` and flip the adjustment's status."""
    validated = dict(row.validated or {})
    adjustments = [dict(a) for a in validated.get("adjustments") or []]
    target = next((a for a in adjustments if a["id"] == adj_id), None)
    if target is None:
        raise AdjustmentNotFound(f"Adjustment {adj_id} not found on this debrief.")
    if target.get("status") == STATUS_OUT_OF_BOUNDS:
        raise AdjustmentOutOfBounds(target.get("validation_note") or "This adjustment is out of bounds and cannot be accepted.")
    if target.get("status") in (STATUS_ACCEPTED, STATUS_DISMISSED):
        raise AdjustmentAlreadyDecided(f"Adjustment already {target['status']}.")

    affected: List[str] = []
    if decision == "accept":
        affected = _apply_adjustment(db, row.user_id, row.for_date, target)
        target["status"] = STATUS_ACCEPTED
    else:
        target["status"] = STATUS_DISMISSED

    decisions = dict(row.decisions or {})
    decisions[adj_id] = {
        "decision": decision,
        "op": target["op"],
        "params": target.get("params") or {},
        "affected_planned_hunt_ids": affected,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    validated["adjustments"] = adjustments
    row.validated = validated          # reassign so the JSON column is marked dirty
    row.decisions = decisions
    db.commit()
    db.refresh(row)
    return row


__all__ = [
    "AdjustmentAlreadyDecided",
    "AdjustmentNotFound",
    "AdjustmentOutOfBounds",
    "ApplierUnavailable",
    "DEBRIEF_MODEL",
    "PROMPT_VERSION",
    "apply_decision",
    "assemble_validated",
    "build_anthropic_client",
    "build_candidates",
    "debrief_to_response",
    "default_week_start",
    "engine_summary",
    "generation_allowed",
    "get_or_create_debrief",
    "run_model",
    "validate_adjustments",
]
