"""
PR Gate engine (ARISE v2 spec §6, v3 §10).

Spawn (§6.2): evaluated on workout create (after PR detection) and lazily on
GET /gates — the latter stands in for the spec's nightly job since this
backend has no scheduler infrastructure (deliberate: no new infra for a solo
deploy; the Status tab hits GET /gates on every open, so gates spawn at
least daily in practice).

v3 (§10): lifts are grouped by **exercise family** (a Saturday back squat
and a Sunday alias are one weekly point); the baseline is the **campaign
best** (best e1RM since the active campaign's ``start_date``, else the last
12 weeks) so an old heavy single no longer blocks a 5×5 trajectory; a gate
needs 4 weekly points (fit over 6); with a Campaign the gate is spawned
**onto the next planned hunt** containing that family, window = hunt + 7
days; and when more lifts qualify than slots, lifts with an active strength
objective win (§4.6 item 1).

Clear (§6.4): hooked into all ingest paths right after
detect_and_create_prs — any working (non-warm-up) set with e1rm >= target on
the gate's family clears it, awards XP immediately (no claim step), and the
create response carries ``gate_cleared`` (§10.5).

Expiry: window passed → quiet row move to history. No penalty, no nag.
"""
import statistics
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.e1rm import calculate_e1rm
from app.core.utils import ensure_utc
from app.models.campaign import PlannedHunt
from app.models.exercise import Exercise
from app.models.gate import GateRank, GateStatus, PRGate
from app.models.user import UserProfile
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services import training_load_service
from app.services.condition_service import CONDITION_BATTLE_READY_MIN, compute_condition
from app.services.exercise_family_service import families_for_user, family_for_exercise
from app.services.pr_detection import get_canonical_exercise_ids
from app.services.training_load_service import local_date_window_filter
from app.services.trend_service import (
    projected_e1rm as project_e1rm,
)
from app.services.trend_service import (
    weekly_best_e1rm_series,
    weekly_slope,
)
from app.services.xp_service import award_xp

# ── Spawn constants (spec §6.2 / §10) ──
GATE_WINDOW_DAYS = 14          # window when no Campaign exists
GATE_PLAN_GRACE_DAYS = 7       # with a plan: window = planned hunt + this (§10.3)
BASELINE_FALLBACK_DAYS = 84    # baseline lookback before a Campaign exists (§10.1)
STALE_LIFT_DAYS = 14           # no projection from a lift not trained this recently
MAX_OPEN_GATES_TOTAL = 2       # scarcity keeps them special
SPAWN_MIN_FACTOR = 1.01        # projected e1RM must beat baseline × this
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

# Short lift labels for generated gate names, keyed by family slug; other
# families use their display name.
_SHORT_NAMES = {
    "back_squat": "Squat",
    "bench_press": "Bench",
    "deadlift": "Deadlift",
    "overhead_press": "OHP",
    "incline_bench_press": "Incline",
    "front_squat": "Front Squat",
    "barbell_row": "Row",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Cross-workstream shims (lazy; fallbacks removed at the freeze) ──────────

def _next_planned_hunt_with_family(
    db: Session, user_id: str, family_id: str, after: date
) -> Optional[PlannedHunt]:
    """W1's ``campaign_service.next_planned_hunt_with_family``; fallback: None
    (no plan to spawn onto → the 14-day window)."""
    try:
        from app.services.campaign_service import next_planned_hunt_with_family
    except ImportError:
        return None
    return next_planned_hunt_with_family(db, user_id, family_id, after=after)


def _active_strength_goal_families(db: Session, user_id: str) -> set:
    """W1's ``goal_service.active_strength_goal_families``; fallback: empty set."""
    try:
        from app.services.goal_service import active_strength_goal_families
    except ImportError:
        return set()
    return set(active_strength_goal_families(db, user_id))


def _template_families_fallback(template: Any) -> Dict[str, List[str]]:
    """Read ``hunt_templates.items`` (spec §4.2 shape) grouped by role."""
    out: Dict[str, List[str]] = {"main": [], "secondary": [], "accessory": []}
    for item in (getattr(template, "items", None) or []):
        if not isinstance(item, dict) or not item.get("family"):
            continue
        out.setdefault(item.get("role") or "accessory", []).append(item["family"])
    return out


def _template_families(template: Any) -> Dict[str, List[str]]:
    """W1's ``campaign_service.template_families``; fallback: parse items."""
    try:
        from app.services.campaign_service import template_families
    except ImportError:
        return _template_families_fallback(template)
    return template_families(template)


# ── Lifecycle helpers ───────────────────────────────────────────────────────

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


def _preferred_reps(db: Session, user_id: str, exercise_ids: List[str], today: date) -> int:
    """Median reps of the user's recent (4-week) working sets, clamped 1-8."""
    rows = (
        db.query(Set.reps)
        .join(WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            local_date_window_filter(today - timedelta(days=28), today),
            WorkoutExercise.exercise_id.in_(exercise_ids),
            Set.reps.isnot(None),
            Set.is_warmup.is_(False),
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


def _short_lift_name(family_id: str, display_name: str) -> str:
    """Short display label for gate names ("Bench 225×4")."""
    return _SHORT_NAMES.get(family_id, display_name)


def _candidate_lifts(db: Session, user_id: str, since: date) -> List[Dict[str, Any]]:
    """Families the user trains, with their campaign-best baseline (§10.1-2).

    One entry per family: {family_id, display_name, root_id, name,
    exercise_ids, baseline, is_big_three, increment_lb}. ``root_id`` is the
    family's most-logged exercise (the gate's ``exercise_id``); ``baseline``
    is the best working-set e1RM on any exercise in the family whose local
    day is on/after ``since``. Families with no e1RM since then are skipped.
    """
    families = families_for_user(db, user_id)
    if not families:
        return []
    all_ids = sorted({eid for fam in families for eid in fam["exercise_ids"]})

    base_query = (
        db.query(WorkoutExercise.exercise_id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutExercise.exercise_id.in_(all_ids),
            Set.is_warmup.is_(False),
        )
    )
    set_counts = dict(
        base_query.add_columns(func.count(Set.id))
        .group_by(WorkoutExercise.exercise_id)
        .all()
    )
    best_since = dict(
        base_query.add_columns(func.max(Set.e1rm))
        .filter(Set.e1rm.isnot(None), local_date_window_filter(since, None))
        .group_by(WorkoutExercise.exercise_id)
        .all()
    )
    names = dict(db.query(Exercise.id, Exercise.name).filter(Exercise.id.in_(all_ids)).all())

    candidates: List[Dict[str, Any]] = []
    for fam in families:
        ids = fam["exercise_ids"]
        baseline = max((best_since.get(eid) or 0.0 for eid in ids), default=0.0)
        if baseline <= 0:
            continue
        root_id = sorted(ids, key=lambda eid: (-set_counts.get(eid, 0), eid))[0]
        candidates.append({
            "family_id": fam["family_id"],
            "display_name": fam["display_name"],
            "root_id": root_id,
            "name": names.get(root_id, fam["display_name"]),
            "exercise_ids": ids,
            "baseline": float(baseline),
            "is_big_three": bool(fam["is_big_three"]),
            "increment_lb": fam["increment_lb"],
        })
    return candidates


def evaluate_gate_spawns(
    db: Session, user_id: str, client_date: Optional[date] = None
) -> List[PRGate]:
    """Run the spawn rules (§6.2 / §10); returns newly spawned gates (committed).

    Also expires overdue gates first, so a single GET /gates keeps the whole
    lifecycle current. ``client_date`` pins the Condition gate (rule 3) and
    "today" to the user's local day — without it an evening evaluation reads
    a mostly-empty UTC "today" (v2.1, QA W2).
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

    now = _now()
    today = client_date or now.date()

    # §10.1: baseline = campaign best; before a Campaign exists, last 12 weeks.
    campaign = training_load_service._get_active_campaign(db, user_id)
    if campaign is not None and campaign.start_date is not None:
        since = campaign.start_date
    else:
        since = today - timedelta(days=BASELINE_FALLBACK_DAYS)

    # §4.6 item 1: lifts with an active strength objective take the slot first.
    objective_families = _active_strength_goal_families(db, user_id)
    candidates = _candidate_lifts(db, user_id, since)
    candidates.sort(key=lambda c: 0 if c["family_id"] in objective_families else 1)

    taken_families = {g.family_id for g in live_gates if g.family_id}
    taken_exercises = {g.exercise_id for g in live_gates}
    spawned: List[PRGate] = []

    for lift in candidates:
        if slots <= 0:
            break
        if lift["family_id"] in taken_families or lift["root_id"] in taken_exercises:
            continue  # rule 4: at most one open gate per lift

        series = weekly_best_e1rm_series(db, user_id, lift["exercise_ids"])
        slope = weekly_slope(series)
        if slope is None or slope <= 0:
            continue  # <4 weekly points, or not improving (§10.2)
        # Projection from stale data is meaningless — require training on
        # this lift within the current or previous week.
        last_week = series[-1][0]
        if (today - last_week).days > STALE_LIFT_DAYS:
            continue
        current = series[-1][1]

        # §10.3: spawn onto the next planned hunt containing the family;
        # window = that hunt + 7 days (end of day). No plan → 14 days.
        hunt = None
        if campaign is not None:
            hunt = _next_planned_hunt_with_family(db, user_id, lift["family_id"], today)
        if hunt is not None:
            expires_at = datetime.combine(
                hunt.date + timedelta(days=GATE_PLAN_GRACE_DAYS),
                time(23, 59, 59),
                tzinfo=timezone.utc,
            )
            window_days = max(1, (expires_at.date() - today).days)
        else:
            expires_at = now + timedelta(days=GATE_WINDOW_DAYS)
            window_days = GATE_WINDOW_DAYS

        projected = project_e1rm(current, slope, window_days)
        baseline = lift["baseline"]
        if projected < baseline * SPAWN_MIN_FACTOR:
            continue  # rule 2: no real PR projected inside the window

        low = baseline * SPAWN_MIN_FACTOR
        high = max(low, projected * TARGET_MAX_FACTOR)
        target = _select_target_set(
            low, high, _preferred_reps(db, user_id, lift["exercise_ids"], today)
        )
        if target is None:
            continue
        target_weight, target_reps, target_e1rm = target

        rank = _rank_for_gain(target_e1rm, baseline, lift["is_big_three"])
        short = _short_lift_name(lift["family_id"], lift["display_name"])

        gate = PRGate(
            user_id=user_id,
            exercise_id=lift["root_id"],
            family_id=lift["family_id"],
            planned_hunt_id=hunt.id if hunt is not None else None,
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
            expires_at=expires_at,
        )
        db.add(gate)
        spawned.append(gate)
        taken_families.add(lift["family_id"])
        slots -= 1

    db.commit()
    for gate in spawned:
        db.refresh(gate)
    return spawned


def _set_e1rm(set_row: Set) -> Optional[float]:
    """The set's e1RM: the stored value, else Epley on ``weight_lb`` × reps."""
    if set_row.e1rm is not None:
        return float(set_row.e1rm)
    weight = set_row.weight_lb if set_row.weight_lb is not None else set_row.weight
    if weight and set_row.reps:
        return calculate_e1rm(float(weight), int(set_row.reps))
    return None


def check_gate_clear(
    db: Session,
    user_id: str,
    workout_exercise: WorkoutExercise,
    sets: List[Set],
) -> List[Dict[str, Any]]:
    """Clear-detection (§6.4) — call right after detect_and_create_prs.

    Any **working** set (warm-ups never clear a gate) with e1rm >= target on
    the gate's family — or, for pre-v3 gates without a family, the gate's
    canonical lift — clears it: XP through award_xp immediately, no claim
    step. Returns one dict per cleared gate: {gate, xp_award}.
    """
    working = [s for s in sets if not s.is_warmup]
    if not working:
        return []

    family_id = family_for_exercise(db, workout_exercise.exercise_id)
    canonical_ids = set(get_canonical_exercise_ids(db, workout_exercise.exercise_id))

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
        same_family = (
            gate.family_id is not None and family_id is not None and gate.family_id == family_id
        )
        if not same_family and gate.exercise_id not in canonical_ids:
            continue
        if ensure_utc(gate.expires_at) < now:
            continue  # past window — expiry sweep will catch it
        clearing_set = None
        for s in working:
            e1rm = _set_e1rm(s)
            if e1rm is not None and e1rm >= gate.target_e1rm:
                clearing_set = s
                break
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


def _prescription_families(prescription: Optional[Dict[str, Any]]) -> set:
    """main/secondary family ids named by a stored prescription (§15.3)."""
    exercises = (prescription or {}).get("exercises") or []
    return {
        e.get("family_id")
        for e in exercises
        if isinstance(e, dict) and e.get("family_id") and e.get("role") in ("main", "secondary")
    }


def gate_for_planned_hunt(
    db: Session, user_id: str, planned_hunt: PlannedHunt
) -> Optional[PRGate]:
    """The open/active gate this hunt should carry as its attempt (§10.3-4).

    Matches the gate spawned onto this hunt, else any live gate whose family
    is a main/secondary family of the hunt's template (fallback: the stored
    prescription) and whose window covers ``planned_hunt.date``.
    """
    live = get_live_gates(db, user_id)
    if not live:
        return None
    for gate in live:
        if gate.planned_hunt_id is not None and gate.planned_hunt_id == planned_hunt.id:
            return gate

    hunt_families: set = set()
    template = getattr(planned_hunt, "template", None)
    if template is not None:
        by_role = _template_families(template)
        hunt_families = set(by_role.get("main", [])) | set(by_role.get("secondary", []))
    if not hunt_families:
        hunt_families = _prescription_families(planned_hunt.prescription)
    if not hunt_families:
        return None

    for gate in live:
        if gate.family_id not in hunt_families:
            continue
        opens = ensure_utc(gate.spawned_at).date()
        closes = ensure_utc(gate.expires_at).date()
        if opens <= planned_hunt.date <= closes:
            return gate
    return None


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
