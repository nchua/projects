"""
Training load — one currency (ARISE v3 spec §6.1–6.3).

Per session, one ``load`` number (Edwards TRIMP for cardio with HR zones,
Foster session-RPE for lifts, documented fallbacks flagged ``estimated``) and
``miles`` kept separately because the guard's rules are stated in miles.
WHOOP ``strain`` is display-only and never enters load.

The daily series (``daily_training_load``) buckets on ``local_date`` (spec
§12 0b) and carries 7- / 28-day EWMAs of run load and total load. ACWR is
**run-only** with a 28-day cold start: a heavy Sat/Sun lifting weekend spikes
total load every Monday and that is the plan working, not a risk signal.

This module also owns the ``local_date`` reader helpers the other W2 files
share (``local_day``, ``session_local_day``, ``local_date_window_filter``):
``date`` stays the instant, ``local_date`` is the bucketing axis, and a NULL
``local_date`` falls back to ``core.utils.derive_local_date`` (midnight
convention) and finally the UTC calendar day.

Cross-workstream reads (W1's ``campaign_service`` / ``prescription_service``)
are lazy imports with neutral fallbacks so this module works before W1 lands;
the orchestrator removes the fallbacks at the contract freeze.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.exertion import ZONE_WEIGHTS
from app.core.utils import derive_local_date, ensure_utc
from app.models.campaign import Campaign, CampaignStatus, PlannedHunt
from app.models.training_load import DailyTrainingLoad
from app.models.workout import WorkoutExercise, WorkoutSession

# ── Load formulas (spec §6.1) ───────────────────────────────────────────────
METERS_PER_MILE = 1609.344
# Cardio without HR zones: duration × this, flagged estimated.
CARDIO_LOAD_PER_MINUTE_FALLBACK = 2.5
# Lift without any RPE: Σ working sets × this × duration_hours, flagged estimated.
LIFT_LOAD_PER_SET_HOUR = 6.0
# Lift with no recorded duration at all: assume this many minutes, flagged estimated.
LIFT_DEFAULT_DURATION_MINUTES = 45.0

# ── Daily series (spec §6.2) ────────────────────────────────────────────────
ACUTE_DAYS = 7
CHRONIC_DAYS = 28
ACUTE_ALPHA = 2.0 / (ACUTE_DAYS + 1)
CHRONIC_ALPHA = 2.0 / (CHRONIC_DAYS + 1)
ACWR_COLD_START_DAYS = 28      # no ACWR until the first run-type session is this old
RECOMPUTE_WINDOW_DAYS = 35     # trailing days rewritten on every recompute
SERIES_DAYS = 28               # GET /load series length
TRAILING_WEEK_DAYS = 7         # miles_7d / longest_run_7d window (inclusive)

# ── Guard thresholds (spec §6.3) — the one block the rules read ─────────────
RAMP_HIGH_FACTOR = 1.20            # miles_7d > factor × miles_plan_7d …
RAMP_HIGH_MIN_MILES = 8.0          # … and miles_7d > this (needs a plan)
LONG_RUN_SHARE_MIN_WEEK_MILES = 15.0   # below this the plan's long_run_miles rules
LONG_RUN_SHARE_MAX = 0.40          # longest_run_7d > share × miles_7d
RUN_ACWR_HIGH = 1.30
RUN_ACWR_CRITICAL = 1.50
DELOAD_LIFT_VERDICTS_FOR_DELOAD = 2    # two `deload_lift` verdicts in one week

FLAG_RAMP_HIGH = "ramp_high"
FLAG_LONG_RUN_SHARE = "long_run_share"
FLAG_RUN_ACWR_HIGH = "run_acwr_high"
FLAG_RUN_ACWR_CRITICAL = "run_acwr_critical"
FLAG_DELOAD_DUE = "deload_due"
ALL_FLAGS = (
    FLAG_RAMP_HIGH,
    FLAG_LONG_RUN_SHARE,
    FLAG_RUN_ACWR_HIGH,
    FLAG_RUN_ACWR_CRITICAL,
    FLAG_DELOAD_DUE,
)

BAND_COLD_START = "cold_start"
BAND_OK = "ok"
BAND_HIGH = "high"
BAND_CRITICAL = "critical"

# Activity types that count toward running mileage — mirrors
# ``api/calendar._RUN_KEYWORDS`` (kept local so a service never imports an
# api module). Case-insensitive substring match on the HealthKit vocab.
_RUN_KEYWORDS = ("run", "running", "jog")


# ── local_date reader helpers (spec §12 0b) ─────────────────────────────────

def local_day(local_date: Optional[date], instant: Optional[datetime]) -> Optional[date]:
    """The bucketing day for a (local_date, date) pair.

    ``local_date`` when stamped; else the midnight convention on ``date``
    (``derive_local_date``); else the UTC calendar day of the instant. The
    last step is the documented service-side fallback for legacy watch rows —
    services have no client tz offset, so the UTC day is the best available.
    """
    if local_date is not None:
        return local_date
    if instant is None:
        return None
    return derive_local_date(instant) or instant.date()


def session_local_day(session: WorkoutSession) -> date:
    """``local_day`` for a ``WorkoutSession`` row."""
    return local_day(session.local_date, session.date)  # type: ignore[return-value]


def local_date_window_filter(start: Optional[date], end: Optional[date]):
    """SQL clause selecting sessions whose local day lies in [start, end].

    Stamped rows match on ``local_date``; NULL rows match on the instant's
    UTC calendar day (``date >= start 00:00`` and ``date < end+1 00:00``) —
    the same fallback ``local_day`` applies in Python, so SQL-level filters
    and Python-side bucketing agree. Either bound may be None (open-ended).
    """
    stamped = []
    legacy = [WorkoutSession.local_date.is_(None)]
    if start is not None:
        stamped.append(WorkoutSession.local_date >= start)
        legacy.append(WorkoutSession.date >= datetime.combine(start, time.min))
    if end is not None:
        stamped.append(WorkoutSession.local_date <= end)
        legacy.append(
            WorkoutSession.date < datetime.combine(end + timedelta(days=1), time.min)
        )
    if not stamped:
        return or_(WorkoutSession.local_date.isnot(None), and_(*legacy))
    return or_(and_(*stamped), and_(*legacy))


def set_weight_lb(set_row: Any) -> float:
    """A set's weight in lb: ``weight_lb`` when backfilled, else ``weight``."""
    if set_row.weight_lb is not None:
        return float(set_row.weight_lb)
    return float(set_row.weight or 0.0)


# ── Session classification ──────────────────────────────────────────────────

def is_run_activity(activity_type: Optional[str]) -> bool:
    """``api/calendar._is_run`` semantics: run/running/jog in the activity type."""
    if not activity_type:
        return False
    lowered = activity_type.lower()
    return any(k in lowered for k in _RUN_KEYWORDS)


def is_run_session(session: WorkoutSession) -> bool:
    """Run-type for miles and ACWR purposes.

    Rule: ``activity_type`` names a run, **or** the row predates
    ``activity_type`` (NULL) but carries a distance — the same rule the
    calendar reader uses for its ``is_run`` badge, so the two surfaces agree.
    A typed walk/hike/ride with a distance is **not** mileage: a dog walk is
    not running load.
    """
    if is_run_activity(session.activity_type):
        return True
    return session.activity_type is None and session.distance_meters is not None


def session_miles(session: WorkoutSession) -> float:
    """Miles for a run-type session (0 for everything else)."""
    if not is_run_session(session) or not session.distance_meters:
        return 0.0
    return float(session.distance_meters) / METERS_PER_MILE


def _duration_minutes(session: WorkoutSession) -> Optional[float]:
    """Exact seconds when present (LogView v2 §7.5), else the rounded minutes."""
    if session.duration_seconds:
        return float(session.duration_seconds) / 60.0
    if session.duration_minutes:
        return float(session.duration_minutes)
    return None


def _all_sets(session: WorkoutSession) -> List[Any]:
    return [s for we in (session.workout_exercises or []) for s in (we.sets or [])]


def trimp(hr_zone_seconds: Optional[Dict[str, Any]]) -> Optional[float]:
    """Edwards TRIMP: Σ zone_minutes × zone_weight, z1..z5 = 1..5.

    ``None`` when there is no usable zone time (so callers fall back).
    """
    if not hr_zone_seconds:
        return None
    total_seconds = 0.0
    weighted_minutes = 0.0
    for zone, seconds in hr_zone_seconds.items():
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            continue
        weight = ZONE_WEIGHTS.get(str(zone).lower())
        if weight is None:
            continue
        total_seconds += seconds
        weighted_minutes += (seconds / 60.0) * weight
    if total_seconds <= 0:
        return None
    return round(weighted_minutes, 2)


def cardio_session_load(session: WorkoutSession) -> Tuple[float, bool]:
    """Cardio formula only (TRIMP, else duration × 2.5 flagged estimated).

    Exposed for ``cooldown_service``, which needs the cardio number for a
    set-less activity exercise regardless of what else the session holds.
    """
    value = trimp(session.hr_zone_seconds)
    if value is not None:
        return value, False
    minutes = _duration_minutes(session)
    if minutes is None:
        return 0.0, True
    return round(minutes * CARDIO_LOAD_PER_MINUTE_FALLBACK, 2), True


def lift_session_load(session: WorkoutSession) -> Tuple[float, bool]:
    """Foster session-RPE: (session_rpe or mean working-set RPE) × minutes.

    No RPE anywhere → Σ working sets × 6 × hours, estimated. No duration →
    45 minutes assumed, estimated. Warm-up sets never count.
    """
    working = [s for s in _all_sets(session) if not s.is_warmup]
    estimated = False
    minutes = _duration_minutes(session)
    if minutes is None:
        minutes = LIFT_DEFAULT_DURATION_MINUTES
        estimated = True

    rpe: Optional[float] = None
    if session.session_rpe:
        rpe = float(session.session_rpe)
    else:
        set_rpes = [float(s.rpe) for s in working if s.rpe is not None]
        if set_rpes:
            rpe = sum(set_rpes) / len(set_rpes)

    if rpe is not None:
        return round(rpe * minutes, 2), estimated
    return round(len(working) * LIFT_LOAD_PER_SET_HOUR * minutes / 60.0, 2), True


def session_load(session: WorkoutSession) -> Tuple[float, bool]:
    """One load number per session per spec §6.1 → ``(load, estimated)``.

    A session with any set is a lift (session-RPE); a set-less session is
    cardio (TRIMP). ``session.workout_exercises`` must be loaded (joinedload
    before calling — CLAUDE.md rule).
    """
    if _all_sets(session):
        return lift_session_load(session)
    return cardio_session_load(session)


# ── Cross-workstream shims (lazy; fallbacks removed at the freeze) ──────────

def _get_active_campaign(db: Session, user_id: str) -> Optional[Campaign]:
    """W1's ``campaign_service.get_active_campaign``; fallback: direct query.

    The fallback is the same semantics (newest ``active`` campaign) so the
    deload cadence works before W1 lands.
    """
    try:
        from app.services.campaign_service import get_active_campaign
    except ImportError:
        return (
            db.query(Campaign)
            .filter(
                Campaign.user_id == user_id,
                Campaign.status == CampaignStatus.ACTIVE.value,
            )
            .order_by(Campaign.start_date.desc())
            .first()
        )
    return get_active_campaign(db, user_id)


def _progression_verdicts(db: Session, user_id: str, week_start: date) -> List[Dict[str, Any]]:
    """W1's ``prescription_service.progression_verdicts``; fallback: ``[]``."""
    try:
        from app.services.prescription_service import progression_verdicts
    except ImportError:
        return []
    return progression_verdicts(db, user_id, week_start)


# ── Plan reads ──────────────────────────────────────────────────────────────

def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _plan_miles_by_week(db: Session, user_id: str, weeks: List[date]) -> Dict[date, Optional[float]]:
    """``planned_hunts.week_target_miles`` per Monday (None when no row/campaign)."""
    if not weeks:
        return {}
    rows = (
        db.query(PlannedHunt.week_start, func.max(PlannedHunt.week_target_miles))
        .filter(PlannedHunt.user_id == user_id, PlannedHunt.week_start.in_(weeks))
        .group_by(PlannedHunt.week_start)
        .all()
    )
    found = {ws: (float(miles) if miles is not None else None) for ws, miles in rows}
    return {ws: found.get(ws) for ws in weeks}


def arc_deload_week(campaign: Campaign, week_start: date) -> bool:
    """True when ``week_start`` is a cadence deload week of the campaign's arcs.

    Weeks count from the Monday of ``campaign.start_date``; every
    ``deload_every_n_weeks``-th week inside an arc deloads (spec §5.2).
    ``overrides["deload_weeks"]`` (the Coach's accepted deload_now) is honored
    too. Weeks beyond the last arc never deload.
    """
    overrides = campaign.overrides or {}
    if week_start.isoformat() in (overrides.get("deload_weeks") or []):
        return True
    if campaign.start_date is None:
        return False
    week_index = (week_start - _week_start(campaign.start_date)).days // 7
    if week_index < 0:
        return False
    for arc in sorted(campaign.arcs or [], key=lambda a: a.index):
        if week_index < arc.weeks:
            cadence = arc.deload_every_n_weeks or 0
            return cadence > 0 and (week_index + 1) % cadence == 0
        week_index -= arc.weeks
    return False


def deload_due_for_week(db: Session, user_id: str, week_start: date) -> bool:
    """§6.3 ``deload_due``: arc cadence, or two ``deload_lift`` verdicts this week."""
    campaign = _get_active_campaign(db, user_id)
    if campaign is not None and arc_deload_week(campaign, week_start):
        return True
    verdicts = _progression_verdicts(db, user_id, week_start)
    deloads = sum(1 for v in verdicts if v.get("verdict") == "deload_lift")
    return deloads >= DELOAD_LIFT_VERDICTS_FOR_DELOAD


# ── Series math ─────────────────────────────────────────────────────────────

def _ewma(values: List[float], alpha: float) -> List[float]:
    """Bias-corrected EWMA (pandas ``adjust=True``) over a daily series.

    Recursive form: num = x + (1-α)·num, den = 1 + (1-α)·den, ewma = num/den.
    Unlike a zero-seeded EWMA this carries no start-up bias, so on the first
    day ACWR is allowed (day 28) the chronic value is honest rather than ~13%
    low. A rest day decays the average rather than cliff-dropping it.
    """
    out: List[float] = []
    num = 0.0
    den = 0.0
    keep = 1.0 - alpha
    for x in values:
        num = x + keep * num
        den = 1.0 + keep * den
        out.append(num / den)
    return out


def flags_for_day(
    *,
    miles_7d: float,
    miles_plan_7d: Optional[float],
    longest_run_7d: float,
    run_acwr: Optional[float],
    deload_due: bool,
) -> List[str]:
    """Evaluate the §6.3 rule table for one day; returns the flag subset."""
    flags: List[str] = []
    if (
        miles_plan_7d is not None
        and miles_7d > RAMP_HIGH_FACTOR * miles_plan_7d
        and miles_7d > RAMP_HIGH_MIN_MILES
    ):
        flags.append(FLAG_RAMP_HIGH)
    if miles_7d >= LONG_RUN_SHARE_MIN_WEEK_MILES and longest_run_7d > LONG_RUN_SHARE_MAX * miles_7d:
        flags.append(FLAG_LONG_RUN_SHARE)
    if run_acwr is not None:
        # Both thresholds are independent rules: a critical day is also high.
        if run_acwr > RUN_ACWR_HIGH:
            flags.append(FLAG_RUN_ACWR_HIGH)
        if run_acwr > RUN_ACWR_CRITICAL:
            flags.append(FLAG_RUN_ACWR_CRITICAL)
    if deload_due:
        flags.append(FLAG_DELOAD_DUE)
    return flags


def band_for_acwr(run_acwr: Optional[float]) -> str:
    if run_acwr is None:
        return BAND_COLD_START
    if run_acwr > RUN_ACWR_CRITICAL:
        return BAND_CRITICAL
    if run_acwr > RUN_ACWR_HIGH:
        return BAND_HIGH
    return BAND_OK


def _empty_day(day: date) -> Dict[str, Any]:
    return {
        "local_date": day,
        "run_load": 0.0,
        "lift_load": 0.0,
        "other_load": 0.0,
        "total_load": 0.0,
        "miles": 0.0,
        "longest_run": 0.0,
        "run_acute_7d": 0.0,
        "run_chronic_28d": 0.0,
        "run_acwr": None,
        "total_acute_7d": 0.0,
        "total_chronic_28d": 0.0,
        "total_acwr": None,
        "miles_7d": 0.0,
        "longest_run_7d": 0.0,
    }


def compute_daily_series(db: Session, user_id: str, through: date) -> Dict[date, Dict[str, Any]]:
    """Full-history daily load series, first session day → ``through``.

    Persists ``training_load`` / ``load_estimated`` on every session as a side
    effect (flushed by the caller). Returns one dict per calendar day keyed
    by local day; days before the first session are absent.
    """
    sessions = (
        db.query(WorkoutSession)
        .options(joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets))
        .filter(WorkoutSession.user_id == user_id, WorkoutSession.deleted_at.is_(None))
        .all()
    )
    per_day: Dict[date, Dict[str, Any]] = {}
    first_run_day: Optional[date] = None
    first_any_day: Optional[date] = None
    for session in sessions:
        load, estimated = session_load(session)
        if session.training_load != load or session.load_estimated is not estimated:
            session.training_load = load
            session.load_estimated = estimated
        day = session_local_day(session)
        if day > through:
            continue
        row = per_day.setdefault(day, _empty_day(day))
        first_any_day = day if first_any_day is None or day < first_any_day else first_any_day
        if _all_sets(session):
            row["lift_load"] += load
        elif is_run_session(session):
            row["run_load"] += load
            miles = session_miles(session)
            row["miles"] += miles
            row["longest_run"] = max(row["longest_run"], miles)
            first_run_day = day if first_run_day is None or day < first_run_day else first_run_day
        else:
            row["other_load"] += load
        row["total_load"] = row["run_load"] + row["lift_load"] + row["other_load"]

    if first_any_day is None:
        return {}

    days: List[date] = []
    cursor = first_any_day
    while cursor <= through:
        days.append(cursor)
        cursor += timedelta(days=1)
    rows = [per_day.get(d) or _empty_day(d) for d in days]

    run_loads = [r["run_load"] for r in rows]
    total_loads = [r["total_load"] for r in rows]
    run_acute = _ewma(run_loads, ACUTE_ALPHA)
    run_chronic = _ewma(run_loads, CHRONIC_ALPHA)
    total_acute = _ewma(total_loads, ACUTE_ALPHA)
    total_chronic = _ewma(total_loads, CHRONIC_ALPHA)

    for i, row in enumerate(rows):
        day = row["local_date"]
        row["run_acute_7d"] = round(run_acute[i], 3)
        row["run_chronic_28d"] = round(run_chronic[i], 3)
        row["total_acute_7d"] = round(total_acute[i], 3)
        row["total_chronic_28d"] = round(total_chronic[i], 3)
        run_ready = (
            first_run_day is not None
            and (day - first_run_day).days >= ACWR_COLD_START_DAYS
            and run_chronic[i] > 0
        )
        row["run_acwr"] = round(run_acute[i] / run_chronic[i], 3) if run_ready else None
        total_ready = (day - first_any_day).days >= ACWR_COLD_START_DAYS and total_chronic[i] > 0
        row["total_acwr"] = round(total_acute[i] / total_chronic[i], 3) if total_ready else None
        window = rows[max(0, i - TRAILING_WEEK_DAYS + 1): i + 1]
        row["miles_7d"] = round(sum(r["miles"] for r in window), 3)
        row["longest_run_7d"] = round(max(r["longest_run"] for r in window), 3)
        row["total_load"] = round(row["total_load"], 2)
        row["run_load"] = round(row["run_load"], 2)
        row["lift_load"] = round(row["lift_load"], 2)
        row["miles"] = round(row["miles"], 3)

    return {r["local_date"]: r for r in rows}


# ── Persistence ─────────────────────────────────────────────────────────────

def recompute_daily_load(
    db: Session,
    user_id: str,
    *,
    as_of: Optional[date] = None,
    days: int = RECOMPUTE_WINDOW_DAYS,
) -> None:
    """Rewrite ``daily_training_load`` for the trailing ``days`` days to ``as_of``.

    Empty days are written too (zeros, ACWR carried by the EWMA). Flushes but
    never commits — the ingest hook runs inside the caller's transaction.
    """
    as_of = as_of or date.today()
    series = compute_daily_series(db, user_id, as_of)
    db.flush()  # sessions' training_load lands before computed_at is stamped

    start = as_of - timedelta(days=days - 1)
    window = [start + timedelta(days=i) for i in range(days)]
    weeks = sorted({_week_start(d) for d in window})
    plan_miles = _plan_miles_by_week(db, user_id, weeks)
    deload_by_week = {ws: deload_due_for_week(db, user_id, ws) for ws in weeks}

    existing = {
        row.local_date: row
        for row in db.query(DailyTrainingLoad)
        .filter(
            DailyTrainingLoad.user_id == user_id,
            DailyTrainingLoad.local_date >= start,
            DailyTrainingLoad.local_date <= as_of,
        )
        .all()
    }
    computed_at = datetime.now(timezone.utc)
    for day in window:
        values = series.get(day) or _empty_day(day)
        week = _week_start(day)
        flags = flags_for_day(
            miles_7d=values["miles_7d"],
            miles_plan_7d=plan_miles.get(week),
            longest_run_7d=values["longest_run_7d"],
            run_acwr=values["run_acwr"],
            deload_due=deload_by_week[week],
        )
        row = existing.get(day)
        if row is None:
            row = DailyTrainingLoad(user_id=user_id, local_date=day)
            db.add(row)
        row.run_load = values["run_load"]
        row.lift_load = values["lift_load"]
        row.total_load = values["total_load"]
        row.miles = values["miles"]
        row.run_acute_7d = values["run_acute_7d"]
        row.run_chronic_28d = values["run_chronic_28d"]
        row.run_acwr = values["run_acwr"]
        row.total_acute_7d = values["total_acute_7d"]
        row.total_chronic_28d = values["total_chronic_28d"]
        row.total_acwr = values["total_acwr"]
        row.miles_7d = values["miles_7d"]
        row.miles_plan_7d = plan_miles.get(week)
        row.longest_run_7d = values["longest_run_7d"]
        row.flags = flags
        row.computed_at = computed_at
    db.flush()


def _newest_session_update(db: Session, user_id: str) -> Optional[datetime]:
    """Latest ``updated_at`` across the user's sessions, deleted ones included
    (a soft delete must also invalidate the series)."""
    value = (
        db.query(func.max(WorkoutSession.updated_at))
        .filter(WorkoutSession.user_id == user_id)
        .scalar()
    )
    return ensure_utc(value) if value else None


def _series_point(row: DailyTrainingLoad) -> Dict[str, Any]:
    return {
        "local_date": row.local_date.isoformat(),
        "run_load": row.run_load,
        "lift_load": row.lift_load,
        "total_load": row.total_load,
        "miles": row.miles,
        "run_acwr": row.run_acwr,
    }


def get_load_state(db: Session, user_id: str, as_of: date) -> Dict[str, Any]:
    """The load state the guard, Condition and ``GET /load`` read (§15.4 shape).

    Recomputes (and commits) when the ``as_of`` row is missing or older than
    the newest session write; otherwise serves the stored rows.
    """
    row = (
        db.query(DailyTrainingLoad)
        .filter(DailyTrainingLoad.user_id == user_id, DailyTrainingLoad.local_date == as_of)
        .first()
    )
    newest = _newest_session_update(db, user_id)
    stale = row is None or (newest is not None and newest > ensure_utc(row.computed_at))
    if stale:
        recompute_daily_load(db, user_id, as_of=as_of)
        db.commit()
        row = (
            db.query(DailyTrainingLoad)
            .filter(DailyTrainingLoad.user_id == user_id, DailyTrainingLoad.local_date == as_of)
            .first()
        )

    series_start = as_of - timedelta(days=SERIES_DAYS - 1)
    stored = {
        r.local_date: r
        for r in db.query(DailyTrainingLoad)
        .filter(
            DailyTrainingLoad.user_id == user_id,
            DailyTrainingLoad.local_date >= series_start,
            DailyTrainingLoad.local_date <= as_of,
        )
        .all()
    }
    series: List[Dict[str, Any]] = []
    for i in range(SERIES_DAYS):
        day = series_start + timedelta(days=i)
        r = stored.get(day)
        if r is None:
            series.append({
                "local_date": day.isoformat(), "run_load": 0.0, "lift_load": 0.0,
                "total_load": 0.0, "miles": 0.0, "run_acwr": None,
            })
        else:
            series.append(_series_point(r))

    return {
        "as_of": as_of.isoformat(),
        "run_acute_7d": row.run_acute_7d or 0.0,
        "run_chronic_28d": row.run_chronic_28d or 0.0,
        "run_acwr": row.run_acwr,
        "total_acwr": row.total_acwr,
        "band": band_for_acwr(row.run_acwr),
        "miles_7d": row.miles_7d or 0.0,
        "miles_plan_7d": row.miles_plan_7d,
        "longest_run_7d": row.longest_run_7d or 0.0,
        "flags": list(row.flags or []),
        "series": series,
    }


def guard_flags_for_date(db: Session, user_id: str, local_date: date) -> List[str]:
    """The §6.3 flags the Overreach Guard acts on for the user's local day."""
    return get_load_state(db, user_id, local_date)["flags"]
