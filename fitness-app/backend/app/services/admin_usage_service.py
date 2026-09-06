"""
Usage aggregates for the owner console (control-plane spec §9.3).

A dialect-neutral port of ``scripts/usage_snapshot.py``: sessions bucket on
the user's local day (``local_date`` with the ``derive_local_date`` fallback,
via the shared ``local_day`` / ``local_day_sql`` / ``local_date_window_filter``
readers), ISO weeks are computed in Python, and nothing here uses
``date_trunc`` or ``::date`` — so the same code runs on SQLite in tests and
Postgres in prod. Aggregates only: no emails, tokens, or row-level notes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Date, case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import to_naive_utc, utcnow
from app.models.achievement import UserAchievement
from app.models.activity import DailyActivity
from app.models.bodyweight import BodyweightEntry
from app.models.entitlement import UserEntitlement
from app.models.exercise import Exercise
from app.models.gate import PRGate
from app.models.goal import Goal
from app.models.notification import DeviceToken
from app.models.pr import PR
from app.models.scan_balance import ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.user import User
from app.models.whoop import WhoopConnection
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.schemas.admin import (
    ActivityCoverage,
    BigThreeSeries,
    FleetBalances,
    FleetExercises,
    FleetIntegrations,
    FleetUsageResponse,
    FleetUsers,
    FleetWeekSessions,
    LiftWeekPoint,
    RunRow,
    ScanUsage,
    SessionMeta,
    SessionSource,
    TopExercise,
    UnlimitedDriftRow,
    UserIntegrationsUsage,
    UserUsageResponse,
    WeekScans,
    WeekSessions,
)
from app.services.campaign_service import monday_of
from app.services.coach_context_service import run_miles, run_pace_sec
from app.services.entitlement_service import KEY_UNLIMITED, is_active
from app.services.training_load_service import (
    METERS_PER_MILE,
    local_date_window_filter,
    local_day,
    local_day_sql,
)
from app.services.whoop_service import get_connection

# The script's substring rule, kept as-is (looser than ``ExerciseFamily.is_big_three``).
BIG_THREE_KEYWORDS = ("squat", "bench", "deadlift")

TOP_EXERCISES_WEEKS = 12
BIG_THREE_WEEKS = 16
SESSION_META_WEEKS = 12
SCANS_WEEKS = 12
RUNS_WEEKS = 8
COVERAGE_DAYS = 30


# ── shared helpers ──────────────────────────────────────────────────────────

def iso_week_label(d: date) -> str:
    """``2026-W36`` for any day in that ISO week."""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def count_where(condition: Any) -> Any:
    """``SUM(CASE WHEN condition THEN 1 ELSE 0 END)`` — a conditional count."""
    return func.sum(case((condition, 1), else_=0))


def _has(column: Any) -> Any:
    return count_where(column.isnot(None))


def _active_session_filter(user_id: Optional[str], since: Optional[date]) -> List[Any]:
    """Non-deleted sessions, optionally for one user and/or on or after a local day."""
    clauses: List[Any] = [WorkoutSession.deleted_at.is_(None)]
    if user_id is not None:
        clauses.append(WorkoutSession.user_id == user_id)
    if since is not None:
        clauses.append(local_date_window_filter(since, None))
    return clauses


def _count_by(rows: List[Tuple[Any, int]]) -> Dict[str, int]:
    return {str(k): int(n) for k, n in rows}


def purge_eligible_cutoff(now: Optional[datetime] = None) -> datetime:
    """Accounts soft-deleted at or before this instant are past the grace period."""
    return (now or utcnow()) - timedelta(days=settings.PURGE_GRACE_DAYS)


def purge_eligible_at(deleted_at: datetime) -> datetime:
    """When a soft-deleted account becomes purge-eligible."""
    return deleted_at + timedelta(days=settings.PURGE_GRACE_DAYS)


# ── per-user ────────────────────────────────────────────────────────────────

def _sessions_by_week(
    db: Session, user_id: str, since: date
) -> Tuple[List[WeekSessions], Dict[str, int], List[SessionSource]]:
    has_sets = (
        select(Set.id)
        .join(WorkoutExercise, WorkoutExercise.id == Set.workout_exercise_id)
        .where(WorkoutExercise.session_id == WorkoutSession.id)
        .correlate(WorkoutSession)
        .exists()
    )
    rows = (
        db.query(
            WorkoutSession.date,
            WorkoutSession.local_date,
            WorkoutSession.activity_type,
            WorkoutSession.distance_meters,
            WorkoutSession.hr_source,
            WorkoutSession.hk_uuid,
            has_sets.label("has_sets"),
        )
        .filter(*_active_session_filter(user_id, since))
        .all()
    )
    weeks: Dict[str, Counter] = defaultdict(Counter)
    miles: Dict[str, float] = defaultdict(float)
    kinds: Counter = Counter()
    sources: Counter = Counter()
    for r in rows:
        label = iso_week_label(local_day(r.local_date, r.date))
        is_cardio = bool(r.activity_type) or (r.distance_meters or 0) > 0
        kind = "cardio" if is_cardio and not r.has_sets else ("strength" if r.has_sets else "other")
        weeks[label][kind] += 1
        if kind == "cardio":
            miles[label] += (r.distance_meters or 0) / METERS_PER_MILE
        kinds[kind] += 1
        sources[("hk" if r.hk_uuid else "app", r.hr_source or "none")] += 1
    by_week = [
        WeekSessions(week=label, miles=round(miles[label], 2), **weeks[label])
        for label in sorted(weeks)
    ]
    source_rows = [
        SessionSource(origin=origin, hr_source=hr, sessions=n)
        for (origin, hr), n in sorted(sources.items())
    ]
    return by_week, dict(kinds), source_rows


def _top_exercises(db: Session, user_id: str, since: date) -> List[TopExercise]:
    sessions = func.count(func.distinct(WorkoutSession.id)).label("sessions")
    sets = func.count(Set.id).label("sets")
    rows = (
        db.query(
            Exercise.name,
            sessions,
            sets,
            func.max(Set.e1rm).label("best_e1rm"),
            _has(Set.rpe).label("sets_with_rpe"),
            _has(Set.avg_heart_rate).label("sets_with_hr"),
        )
        .select_from(WorkoutSession)
        .join(WorkoutExercise, WorkoutExercise.session_id == WorkoutSession.id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
        .filter(*_active_session_filter(user_id, since))
        .group_by(Exercise.name)
        .order_by(sessions.desc(), sets.desc(), Exercise.name)
        .limit(20)
        .all()
    )
    return [
        TopExercise(
            name=r.name,
            sessions=int(r.sessions),
            sets=int(r.sets),
            best_e1rm=round(float(r.best_e1rm), 1) if r.best_e1rm is not None else None,
            sets_with_rpe=int(r.sets_with_rpe or 0),
            sets_with_hr=int(r.sets_with_hr or 0),
        )
        for r in rows
    ]


def _big_three(db: Session, user_id: str, since: date) -> List[BigThreeSeries]:
    """Weekly best e1RM + set count per big-three lift, from one grouped query."""
    lift = case(
        *[(func.lower(Exercise.name).like(f"%{kw}%"), kw) for kw in BIG_THREE_KEYWORDS],
        else_=None,
    )
    day = local_day_sql()
    rows = (
        db.query(lift.label("lift"), day.label("day"), func.max(Set.e1rm), func.count(Set.id))
        .select_from(WorkoutSession)
        .join(WorkoutExercise, WorkoutExercise.session_id == WorkoutSession.id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
        .filter(*_active_session_filter(user_id, since), lift.isnot(None))
        .group_by(lift, day)
        .all()
    )
    best: Dict[Tuple[str, date], Optional[float]] = {}
    sets: Counter = Counter()
    for lift_name, day_value, best_e1rm, n_sets in rows:
        key = (lift_name, monday_of(day_value))
        sets[key] += int(n_sets or 0)
        if best_e1rm is not None and (best.get(key) is None or best_e1rm > best[key]):
            best[key] = best_e1rm
    out: List[BigThreeSeries] = []
    for keyword in BIG_THREE_KEYWORDS:
        series = [
            LiftWeekPoint(
                week_start=monday,
                best_e1rm=(
                    round(float(best[(keyword, monday)]), 1)
                    if best.get((keyword, monday)) is not None
                    else None
                ),
                sets=sets[(keyword, monday)],
            )
            for monday in sorted(m for (name, m) in sets if name == keyword)
        ]
        out.append(BigThreeSeries(lift=keyword, weeks_with_data=len(series), series=series))
    return out


def _session_meta(db: Session, user_id: str, since: date) -> SessionMeta:
    r = (
        db.query(
            func.count(WorkoutSession.id),
            func.avg(WorkoutSession.duration_minutes),
            _has(WorkoutSession.name),
            _has(WorkoutSession.session_rpe),
            count_where((WorkoutSession.notes.isnot(None)) & (WorkoutSession.notes != "")),
            _has(WorkoutSession.avg_heart_rate),
            _has(WorkoutSession.strain),
            _has(WorkoutSession.mile_splits),
        )
        .filter(*_active_session_filter(user_id, since))
        .one()
    )
    return SessionMeta(
        sessions=int(r[0] or 0),
        avg_duration_minutes=round(float(r[1]), 1) if r[1] is not None else None,
        named=int(r[2] or 0),
        with_session_rpe=int(r[3] or 0),
        with_notes=int(r[4] or 0),
        with_avg_hr=int(r[5] or 0),
        with_strain=int(r[6] or 0),
        with_splits=int(r[7] or 0),
    )


def gates_by_status(db: Session, user_id: str) -> Dict[str, int]:
    """``pr_gates`` rows by status."""
    return _count_by(
        db.query(PRGate.status, func.count(PRGate.id))
        .filter(PRGate.user_id == user_id)
        .group_by(PRGate.status)
        .all()
    )


def goals_by_status(db: Session, user_id: str) -> Dict[str, int]:
    """``goals`` rows by status."""
    return _count_by(
        db.query(Goal.status, func.count(Goal.id))
        .filter(Goal.user_id == user_id)
        .group_by(Goal.status)
        .all()
    )


def _activity_coverage(db: Session, user_id: str, since: date) -> List[ActivityCoverage]:
    rows = (
        db.query(
            DailyActivity.source,
            func.count(func.distinct(DailyActivity.date)),
            _has(DailyActivity.steps),
            _has(DailyActivity.sleep_hours),
            _has(DailyActivity.hrv),
            _has(DailyActivity.resting_heart_rate),
            _has(DailyActivity.recovery_score),
            _has(DailyActivity.strain),
        )
        .filter(DailyActivity.user_id == user_id, DailyActivity.date >= since)
        .group_by(DailyActivity.source)
        .order_by(DailyActivity.source)
        .all()
    )
    return [
        ActivityCoverage(
            source=r[0],
            days=int(r[1] or 0),
            steps=int(r[2] or 0),
            sleep=int(r[3] or 0),
            hrv=int(r[4] or 0),
            resting_hr=int(r[5] or 0),
            recovery=int(r[6] or 0),
            strain=int(r[7] or 0),
        )
        for r in rows
    ]


def active_device_token_count(db: Session, user_id: str) -> int:
    """Active push-registered devices (a count — the token strings never leave the DB)."""
    return int(
        db.query(func.count(DeviceToken.id))
        .filter(DeviceToken.user_id == user_id, DeviceToken.is_active == True)
        .scalar()
        or 0
    )


def _integrations(db: Session, user_id: str) -> UserIntegrationsUsage:
    whoop = get_connection(db, user_id)
    bw = (
        db.query(func.count(BodyweightEntry.id), func.max(BodyweightEntry.date))
        .filter(BodyweightEntry.user_id == user_id)
        .one()
    )
    prs = (
        db.query(func.count(PR.id))
        .filter(PR.user_id == user_id, PR.achieved_at >= to_naive_utc(utcnow() - timedelta(weeks=12)))
        .scalar()
    )
    achievements = (
        db.query(func.count(UserAchievement.id))
        .filter(UserAchievement.user_id == user_id)
        .scalar()
    )
    balance = db.query(ScanBalance).filter(ScanBalance.user_id == user_id).first()
    return UserIntegrationsUsage(
        whoop_connected=whoop is not None,
        whoop_last_synced_at=whoop.last_synced_at if whoop else None,
        whoop_token_expires_at=whoop.expires_at if whoop else None,
        whoop_scope=whoop.scope if whoop else None,
        active_device_tokens=active_device_token_count(db, user_id),
        goals_by_status=goals_by_status(db, user_id),
        bodyweight_entries=int(bw[0] or 0),
        last_bodyweight_date=bw[1],
        prs_last_12_weeks=int(prs or 0),
        achievements_unlocked=int(achievements or 0),
        scan_credits=balance.scan_credits if balance else None,
        has_unlimited=bool(balance.has_unlimited) if balance else False,
    )


def _scan_usage(db: Session, user_id: Optional[str], weeks: int, today: date) -> ScanUsage:
    day = func.date(ScreenshotUsage.created_at, type_=Date)
    query = db.query(
        day.label("day"), func.count(ScreenshotUsage.id), func.sum(ScreenshotUsage.screenshots_count)
    ).filter(ScreenshotUsage.created_at >= datetime.combine(today - timedelta(weeks=weeks), time.min))
    if user_id is not None:
        query = query.filter(ScreenshotUsage.user_id == user_id)
    scans: Counter = Counter()
    shots: Counter = Counter()
    for day_value, n, total in query.group_by(day).all():
        label = iso_week_label(day_value)
        scans[label] += int(n or 0)
        shots[label] += int(total or 0)
    return ScanUsage(
        weeks=weeks,
        scans=sum(scans.values()),
        screenshots=sum(shots.values()),
        by_week=[
            WeekScans(week=label, scans=scans[label], screenshots=shots[label])
            for label in sorted(scans)
        ],
    )


def _runs(db: Session, user_id: str, since: date) -> List[RunRow]:
    sessions = (
        db.query(WorkoutSession)
        .filter(*_active_session_filter(user_id, since), WorkoutSession.distance_meters.isnot(None))
        .order_by(WorkoutSession.date)
        .all()
    )
    out: List[RunRow] = []
    for s in sessions:
        seconds = s.duration_seconds or (s.duration_minutes * 60 if s.duration_minutes else None)
        pace = run_pace_sec(s)
        out.append(
            RunRow(
                local_date=local_day(s.local_date, s.date),
                activity_type=s.activity_type,
                miles=run_miles(s) or 0.0,
                duration_minutes=round(seconds / 60) if seconds else None,
                pace_min_per_mile=round(pace / 60, 1) if pace else None,
                avg_heart_rate=s.avg_heart_rate,
                has_splits=s.mile_splits is not None,
            )
        )
    return out


def user_usage(
    db: Session, user_id: str, *, weeks: int = 20, today: Optional[date] = None
) -> UserUsageResponse:
    """The per-user usage block (spec §9.3). Windows are local-day based."""
    today = today or date.today()
    by_week, kinds, sources = _sessions_by_week(db, user_id, today - timedelta(weeks=weeks))
    return UserUsageResponse(
        user_id=user_id,
        weeks=weeks,
        generated_at=utcnow(),
        sessions_by_week=by_week,
        kinds=kinds,
        sources=sources,
        top_exercises=_top_exercises(db, user_id, today - timedelta(weeks=TOP_EXERCISES_WEEKS)),
        big_three=_big_three(db, user_id, today - timedelta(weeks=BIG_THREE_WEEKS)),
        session_meta=_session_meta(db, user_id, today - timedelta(weeks=SESSION_META_WEEKS)),
        gates_by_status=gates_by_status(db, user_id),
        activity_coverage=_activity_coverage(db, user_id, today - timedelta(days=COVERAGE_DAYS)),
        latest_daily_activity_date=(
            db.query(func.max(DailyActivity.date)).filter(DailyActivity.user_id == user_id).scalar()
        ),
        integrations=_integrations(db, user_id),
        scans=_scan_usage(db, user_id, SCANS_WEEKS, today),
        runs=_runs(db, user_id, today - timedelta(weeks=RUNS_WEEKS)),
    )


# ── fleet ───────────────────────────────────────────────────────────────────

def unlimited_flag_drift(db: Session) -> List[UnlimitedDriftRow]:
    """Balances whose cached ``has_unlimited`` disagrees with the derived entitlement (§6.2)."""
    now = utcnow()
    # Same rule as ``sync_unlimited_flag`` → ``is_entitled``: the NEWEST active
    # row decides, so an explicit newer ``False`` grant is not "entitled".
    newest_active: Dict[str, bool] = {}
    rows = (
        db.query(UserEntitlement)
        .filter(UserEntitlement.key == KEY_UNLIMITED, UserEntitlement.revoked_at.is_(None))
        .order_by(UserEntitlement.created_at.desc(), UserEntitlement.id.desc())
        .all()
    )
    for row in rows:
        if row.user_id not in newest_active and is_active(row, now):
            newest_active[row.user_id] = bool(row.value)
    entitled = {user_id for user_id, value in newest_active.items() if value}
    drift: List[UnlimitedDriftRow] = []
    for user_id, has_unlimited in db.query(ScanBalance.user_id, ScanBalance.has_unlimited).all():
        derived = user_id in entitled
        if bool(has_unlimited) != derived:
            drift.append(
                UnlimitedDriftRow(user_id=user_id, has_unlimited=bool(has_unlimited), derived=derived)
            )
    return drift


def fleet_usage(db: Session, *, weeks: int = 20, today: Optional[date] = None) -> FleetUsageResponse:
    """The fleet rollup behind the Overview screen (spec §9.3)."""
    today = today or date.today()
    now = utcnow()

    total, deleted, admins = db.query(
        func.count(User.id),
        count_where(User.is_deleted == True),
        count_where(User.is_admin == True),
    ).one()
    purge_eligible = (
        db.query(func.count(User.id))
        .filter(
            User.is_deleted == True,
            User.deleted_at.isnot(None),
            User.deleted_at <= to_naive_utc(purge_eligible_cutoff(now)),
        )
        .scalar()
    )

    # Sessions of live users grouped by (user, local day) in SQL; ISO weeks in Python.
    day = local_day_sql()
    live = db.query(WorkoutSession.user_id, day.label("day"), func.count(WorkoutSession.id)).join(
        User, User.id == WorkoutSession.user_id
    ).filter(User.is_deleted == False)
    sessions: Counter = Counter()
    users_by_week: Dict[str, set] = defaultdict(set)
    for user_id, day_value, n in (
        live.filter(*_active_session_filter(None, today - timedelta(weeks=weeks)))
        .group_by(WorkoutSession.user_id, day)
        .all()
    ):
        label = iso_week_label(day_value)
        sessions[label] += int(n or 0)
        users_by_week[label].add(user_id)
    last_day_by_user: Dict[str, date] = dict(
        db.query(WorkoutSession.user_id, func.max(day))
        .join(User, User.id == WorkoutSession.user_id)
        .filter(User.is_deleted == False, *_active_session_filter(None, today - timedelta(days=30)))
        .group_by(WorkoutSession.user_id)
        .all()
    )

    balances = db.query(
        func.count(ScanBalance.id),
        count_where(ScanBalance.has_unlimited == True),
        func.sum(ScanBalance.scan_credits),
    ).one()
    exercises = db.query(
        func.count(Exercise.id),
        count_where(Exercise.is_custom == True),
        count_where(Exercise.family_id.is_(None)),
    ).one()

    return FleetUsageResponse(
        generated_at=now,
        weeks=weeks,
        users=FleetUsers(
            total=int(total or 0),
            deleted=int(deleted or 0),
            admins=int(admins or 0),
            active_7d=sum(1 for d in last_day_by_user.values() if d >= today - timedelta(days=7)),
            active_30d=len(last_day_by_user),
            purge_eligible=int(purge_eligible or 0),
        ),
        sessions_by_week=[
            FleetWeekSessions(
                week=label, sessions=sessions[label], active_users=len(users_by_week[label])
            )
            for label in sorted(sessions)
        ],
        scans_by_week=_scan_usage(db, None, weeks, today).by_week,
        balances=FleetBalances(
            rows=int(balances[0] or 0),
            unlimited_count=int(balances[1] or 0),
            credits_total=int(balances[2] or 0),
        ),
        integrations=FleetIntegrations(
            whoop_connections=int(db.query(func.count(WhoopConnection.id)).scalar() or 0),
            active_device_tokens=int(
                db.query(func.count(DeviceToken.id)).filter(DeviceToken.is_active == True).scalar()
                or 0
            ),
        ),
        exercises=FleetExercises(
            total=int(exercises[0] or 0),
            custom=int(exercises[1] or 0),
            without_family=int(exercises[2] or 0),
        ),
        unlimited_flag_drift=unlimited_flag_drift(db),
    )
