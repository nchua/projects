"""
PR Gate engine (ARISE v2 spec §6).

Spawn (§6.2): evaluated on workout create (after PR detection) and lazily on
GET /gates — the latter stands in for the spec's nightly job since this
backend has no scheduler infrastructure (deliberate: no new infra for a solo
deploy; the Status tab hits GET /gates on every open, so gates spawn at
least daily in practice).

Clear (§6.4): hooked into all three ingest paths right after
detect_and_create_prs — any set with e1rm >= target on the gate's canonical
lift clears it, awards XP immediately (no claim step).

Expiry: window passed → quiet row move to history. No penalty, no nag.
"""
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.utils import ensure_utc
from app.models.gate import GateRank, GateStatus, PRGate
from app.models.user import UserProfile
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services.condition_service import CONDITION_BATTLE_READY_MIN, compute_condition
from app.services.pr_detection import get_canonical_exercise_ids
from app.services.trend_service import (
    projected_e1rm as project_e1rm,
)
from app.services.trend_service import (
    weekly_best_e1rm_series,
    weekly_slope,
)
from app.services.xp_service import BIG_THREE, award_xp

# ── Spawn constants (spec §6.2) ──
GATE_WINDOW_DAYS = 14
MAX_OPEN_GATES_TOTAL = 2       # scarcity keeps them special
SPAWN_MIN_FACTOR = 1.01        # projected_e1rm(14) must beat baseline × this
TARGET_MAX_FACTOR = 1.02       # target band top: projected × this

# ── Ranking (spec §6.3): e1RM gain over baseline → rank, XP on clear ──
# (lower bound inclusive, upper bound exclusive)
RANK_BANDS: List[Tuple[float, float, GateRank]] = [
    (1.010, 1.020, GateRank.C),
    (1.020, 1.035, GateRank.B),
    (1.035, 1.050, GateRank.A),
    (1.050, float("inf"), GateRank.S),
]
GATE_XP = {GateRank.C: 300, GateRank.B: 500, GateRank.A: 800, GateRank.S: 1200}
RANK_ORDER = [GateRank.C, GateRank.B, GateRank.A, GateRank.S]

# Plate-milestone weights preferred for target sets (spec §6.2-5).
PLATE_MILESTONES = {95, 135, 185, 225, 275, 315, 365, 405, 455, 495}

# Short lift labels for generated gate names.
_SHORT_NAMES = {
    "squat": "Squat",
    "bench": "Bench",
    "deadlift": "Deadlift",
    "overhead_press": "OHP",
    "incline_bench": "Incline",
    "row": "Row",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def expire_stale_gates(db: Session, user_id: str) -> int:
    """Move overdue open/active gates to expired (quiet — spec §6.4)."""
    now = _now()
    stale = (
        db.query(PRGate)
        .filter(
            PRGate.user_id == user_id,
            PRGate.status.in_([GateStatus.OPEN.value, GateStatus.ACTIVE.value]),
        )
        .all()
    )
    expired = 0
    for gate in stale:
        if ensure_utc(gate.expires_at) < now:
            gate.status = GateStatus.EXPIRED.value
            expired += 1
    if expired:
        db.flush()
    return expired


def _rank_for_gain(target_e1rm: float, baseline: float, is_big_three: bool) -> GateRank:
    """Rank from the size of the jump; big-three lifts get +1 step (cap S)."""
    ratio = target_e1rm / baseline
    rank = GateRank.C
    for low, high, band_rank in RANK_BANDS:
        if low <= ratio < high:
            rank = band_rank
            break
    if is_big_three:
        rank = RANK_ORDER[min(RANK_ORDER.index(rank) + 1, len(RANK_ORDER) - 1)]
    return rank


def _preferred_reps(db: Session, user_id: str, exercise_ids: List[str]) -> int:
    """Median reps of the user's recent (4-week) working sets, clamped 1-8."""
    cutoff = _now().replace(tzinfo=None) - timedelta(days=28)
    rows = (
        db.query(Set.reps)
        .join(WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= cutoff,
            WorkoutExercise.exercise_id.in_(exercise_ids),
            Set.reps.isnot(None),
        )
        .all()
    )
    reps = [r[0] for r in rows if r[0] and r[0] > 0]
    if not reps:
        return 5
    return max(1, min(8, round(statistics.median(reps))))


def _select_target_set(
    low_e1rm: float, high_e1rm: float, preferred_reps: int
) -> Optional[Tuple[float, int, float]]:
    """Choose (weight, reps, epley_e1rm) whose e1RM lands in the target band.

    Weight in 5 lb increments, reps 1-8, preferring plate-milestone weights
    and rep counts near the user's recent working range (spec §6.2-5).
    """
    best: Optional[Tuple[float, float, int, float]] = None  # (score, w, r, e)
    for reps in range(1, 9):
        epley = 1 + reps / 30.0
        w_low = int(low_e1rm / epley // 5) * 5
        w_high = int(high_e1rm / epley // 5 + 1) * 5
        for weight in range(max(5, w_low), w_high + 5, 5):
            e1rm = round(weight * epley, 2)
            if not (low_e1rm <= e1rm <= high_e1rm):
                continue
            score = 0.0
            if weight in PLATE_MILESTONES:
                score += 10.0
            score -= abs(reps - preferred_reps)
            # Mild preference for the easier end of the band on ties.
            score -= (e1rm - low_e1rm) / max(1.0, high_e1rm - low_e1rm)
            if best is None or score > best[0]:
                best = (score, float(weight), reps, e1rm)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _short_lift_name(exercise_name: str) -> str:
    """Short display label for gate names ("Bench 225×4")."""
    # Local import: analytics is an api module; keep the dependency lazy.
    from app.api.analytics import get_exercise_canonical_id

    key = get_exercise_canonical_id(exercise_name)
    if key and key in _SHORT_NAMES:
        return _SHORT_NAMES[key]
    return exercise_name


def _candidate_lifts(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """Canonical lifts in STRENGTH_STANDARDS the user actually trains.

    One entry per canonical alias group: {root_id, name, exercise_ids,
    baseline} where baseline is the all-time best e1RM across aliases (the
    same aggregation PR detection uses).
    """
    from sqlalchemy import func

    from app.api.analytics import get_exercise_canonical_id
    from app.models.exercise import Exercise

    rows = (
        db.query(
            Exercise.id,
            Exercise.name,
            Exercise.canonical_id,
            func.max(Set.e1rm).label("best_e1rm"),
        )
        .join(WorkoutExercise, WorkoutExercise.exercise_id == Exercise.id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            Set.e1rm.isnot(None),
        )
        .group_by(Exercise.id, Exercise.name, Exercise.canonical_id)
        .all()
    )

    groups: Dict[str, Dict[str, Any]] = {}
    for exercise_id, name, canonical_id, best_e1rm in rows:
        if get_exercise_canonical_id(name) is None:
            continue  # not a lift with strength standards → no gate
        root = canonical_id or exercise_id
        entry = groups.setdefault(root, {
            "root_id": root,
            "name": name,
            "exercise_ids": [],
            "baseline": 0.0,
        })
        entry["exercise_ids"].append(exercise_id)
        if best_e1rm and best_e1rm > entry["baseline"]:
            entry["baseline"] = best_e1rm
            entry["name"] = name
    return [g for g in groups.values() if g["baseline"] > 0]


def evaluate_gate_spawns(
    db: Session, user_id: str, client_date: Optional[date] = None
) -> List[PRGate]:
    """Run the §6.2 spawn rules; returns newly spawned gates (committed).

    Also expires overdue gates first, so a single GET /gates keeps the whole
    lifecycle current. ``client_date`` pins the Condition gate (rule 3) to the
    user's local day — without it an evening evaluation reads a mostly-empty
    UTC "today" (v2.1, QA W2).
    """
    expire_stale_gates(db, user_id)

    live_gates = (
        db.query(PRGate)
        .filter(
            PRGate.user_id == user_id,
            PRGate.status.in_([GateStatus.OPEN.value, GateStatus.ACTIVE.value]),
        )
        .all()
    )
    slots = MAX_OPEN_GATES_TOTAL - len(live_gates)
    if slots <= 0:
        db.commit()
        return []

    # Condition gate (rule 3): today's Condition must be BATTLE READY+.
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    user_age = profile.age if profile else None
    condition = compute_condition(db, user_id, client_date, user_age=user_age)
    if condition["score"] < CONDITION_BATTLE_READY_MIN:
        db.commit()
        return []

    lifts_with_gates = {g.exercise_id for g in live_gates}
    spawned: List[PRGate] = []
    now = _now()

    for lift in _candidate_lifts(db, user_id):
        if slots <= 0:
            break
        if lift["root_id"] in lifts_with_gates:
            continue  # rule 4: at most one open gate per lift

        series = weekly_best_e1rm_series(db, user_id, lift["exercise_ids"])
        slope = weekly_slope(series)
        if slope is None or slope <= 0:
            continue  # <6 weeks of data, or not improving (§6.1)
        # Projection from stale data is meaningless — require training on
        # this lift within the current or previous week.
        last_week = series[-1][0]
        if (now.date() - last_week).days > 14:
            continue

        current = series[-1][1]
        projected = project_e1rm(current, slope, GATE_WINDOW_DAYS)
        baseline = lift["baseline"]
        if projected < baseline * SPAWN_MIN_FACTOR:
            continue  # rule 2: no real PR projected inside the window

        low = baseline * SPAWN_MIN_FACTOR
        high = max(low, projected * TARGET_MAX_FACTOR)
        target = _select_target_set(
            low, high, _preferred_reps(db, user_id, lift["exercise_ids"])
        )
        if target is None:
            continue
        target_weight, target_reps, target_e1rm = target

        is_big_three = any(bt in lift["name"].lower() for bt in BIG_THREE)
        rank = _rank_for_gain(target_e1rm, baseline, is_big_three)
        short = _short_lift_name(lift["name"])

        gate = PRGate(
            user_id=user_id,
            exercise_id=lift["root_id"],
            rank=rank.value,
            name=f"{rank.value}-Rank Gate: {short} {int(target_weight)}×{target_reps}",
            target_weight=target_weight,
            target_reps=target_reps,
            target_e1rm=target_e1rm,
            baseline_e1rm=round(baseline, 2),
            projected_e1rm=projected,
            weekly_slope=slope,
            condition_at_spawn=condition["score"],
            status=GateStatus.OPEN.value,
            spawned_at=now,
            expires_at=now + timedelta(days=GATE_WINDOW_DAYS),
        )
        db.add(gate)
        spawned.append(gate)
        slots -= 1

    db.commit()
    for gate in spawned:
        db.refresh(gate)
    return spawned


def check_gate_clear(
    db: Session,
    user_id: str,
    workout_exercise: WorkoutExercise,
    sets: List[Set],
) -> List[Dict[str, Any]]:
    """Clear-detection (§6.4) — call right after detect_and_create_prs.

    Any set with e1rm >= target_e1rm on the gate's canonical lift clears it:
    XP through award_xp immediately, no claim step. Returns one dict per
    cleared gate: {gate, xp_award}.
    """
    exercise_ids = set(get_canonical_exercise_ids(db, workout_exercise.exercise_id))

    open_gates = (
        db.query(PRGate)
        .filter(
            PRGate.user_id == user_id,
            PRGate.status.in_([GateStatus.OPEN.value, GateStatus.ACTIVE.value]),
        )
        .all()
    )
    cleared: List[Dict[str, Any]] = []
    now = _now()

    for gate in open_gates:
        if gate.exercise_id not in exercise_ids:
            continue
        if ensure_utc(gate.expires_at) < now:
            continue  # past window — expiry sweep will catch it
        clearing_set = next(
            (s for s in sets if s.e1rm is not None and s.e1rm >= gate.target_e1rm),
            None,
        )
        if clearing_set is None:
            continue

        rank = GateRank(gate.rank)
        xp = GATE_XP[rank]
        gate.status = GateStatus.CLEARED.value
        gate.cleared_at = now
        gate.cleared_by_set_id = clearing_set.id
        gate.xp_awarded = xp
        xp_award = award_xp(db, user_id, xp, count_workout=False)
        cleared.append({"gate": gate, "xp_award": xp_award})

    return cleared


def get_live_gates(db: Session, user_id: str) -> List[PRGate]:
    """Open + active gates, freshest first."""
    return (
        db.query(PRGate)
        .filter(
            PRGate.user_id == user_id,
            PRGate.status.in_([GateStatus.OPEN.value, GateStatus.ACTIVE.value]),
        )
        .order_by(PRGate.spawned_at.desc())
        .all()
    )


def get_gate_history(db: Session, user_id: str, limit: int = 20) -> List[PRGate]:
    """Cleared/expired gates, newest first."""
    return (
        db.query(PRGate)
        .filter(
            PRGate.user_id == user_id,
            PRGate.status.in_([GateStatus.CLEARED.value, GateStatus.EXPIRED.value]),
        )
        .order_by(PRGate.spawned_at.desc())
        .limit(limit)
        .all()
    )
