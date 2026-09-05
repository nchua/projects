"""
Prescription engine (ARISE v3 spec §5) — deterministic.

Pure function of (template item, athlete history, readiness, load state) →
concrete sets, with a ``rationale`` carrying the real numbers used. No LLM
in this path; the engine owns every number.

Order of operations inside :func:`prescribe` (spec §5.1, §6.4, §10):

1. **Base** prescription per family: anchor (last session ≤ 21 d → verdict;
   else e1RM-derived start; else no anchor), warm-ups for main lifts, run
   targets from the arc ramp. This is what materialization persists.
2. **Readiness modulation** by Condition band (fetch time only).
3. **Gate attempt** as set 1 after warm-ups (PEAK / BATTLE READY only),
   working sets −10%; STRAINED defers.
4. **Overreach Guard** actions on runs (and ``deload_due`` on main lifts).
5. **System line** (§8.3) from the rationale + the highest-priority flag.
"""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, joinedload

from app.core.utils import KG_TO_LB, derive_local_date, weight_to_lb
from app.models.campaign import HuntType, PlannedHunt
from app.models.exercise import Exercise
from app.models.exercise_family import ExerciseFamily
from app.models.gate import PRGate
from app.models.training_load import DailyTrainingLoad
from app.models.user import UserProfile, WeightUnit
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services.exercise_family_defs import FAMILY_DEFS, normalize_name
from app.services.pr_detection import get_canonical_exercise_ids

PRESCRIPTION_VERSION = 1

# ── Anchor selection (§5.1) ──
ANCHOR_WINDOW_DAYS = 21
E1RM_WINDOW_DAYS = 90
E1RM_MAX_REPS = 8
E1RM_START_FACTOR = 0.90
FIRST_SESSION_TEXT = "first session — pick a load you can finish at RPE 7–8"

# ── Verdicts ──
DELOAD_LIFT_FACTOR = 0.90
GATE_BACKOFF_FACTOR = 0.90
WARMUP_SCHEME: Tuple[Tuple[float, int], ...] = ((0.40, 5), (0.60, 3), (0.80, 2))

# ── Readiness modulation (§5.1 table) ──
STRAINED_MAIN_FACTOR = 0.95
CRITICAL_MAIN_FACTOR = 0.85
CRITICAL_MAIN_SETS = 3
REST_OPTION_LINE = (
    "REST is the other option today — Condition is CRITICAL. "
    "If you hunt, keep it light and stop at the prescribed sets."
)

# ── Overreach Guard (§6.4) ──
ACWR_HIGH_CUT = 0.80
RAMP_CAP_FACTOR = 1.20
LONG_RUN_SHARE_CAP = 0.40
GUARD_VETO_CONDITION = 65
GUARD_PRIORITY: Tuple[str, ...] = (
    "run_acwr_critical", "run_acwr_high", "ramp_high", "long_run_share", "deload_due",
)

# ── Runs (§5.2) ──
DEFAULT_AGE = 30
ZONE2_CEILING = 0.70

BAND_PEAK = "peak"
BAND_BATTLE_READY = "battle_ready"
BAND_STRAINED = "strained"
BAND_CRITICAL = "critical"
BAND_LABELS = {
    BAND_PEAK: "PEAK",
    BAND_BATTLE_READY: "BATTLE READY",
    BAND_STRAINED: "STRAINED",
    BAND_CRITICAL: "CRITICAL",
}


# ═══════════════════════════════════════════════════════════════════════════
# Pure helpers
# ═══════════════════════════════════════════════════════════════════════════

def round_to_increment(
    weight: Optional[float], increment: float, unit: str = "lb"
) -> Optional[float]:
    """Round a lb weight to the family's increment.

    ``unit="kg"`` rounds to the kg equivalents (2.5 kg for a 5 lb family,
    1.25 kg for a 2.5 lb family) but still returns lb — lifts are stored in
    lb (spec §5.1 rounding rule).
    """
    if weight is None:
        return None
    if increment <= 0:
        return round(float(weight), 1)
    if unit == "kg":
        inc_kg = 2.5 if increment >= 5 else 1.25
        kg = float(weight) / KG_TO_LB
        rounded_kg = round(kg / inc_kg) * inc_kg
        return round(rounded_kg * KG_TO_LB, 1)
    return round(round(float(weight) / increment) * increment, 1)


def pct_for_reps(reps: int) -> float:
    """Epley inverse: the fraction of e1RM a clean ``reps``-rep set sits at."""
    return 1.0 / (1.0 + reps / 30.0)


def hr_cap_bpm(age: Optional[int], override: Optional[int]) -> int:
    """Zone-2 ceiling: round(0.70 × (220 − age)); age defaults to 30; override wins."""
    if override:
        return int(override)
    return int(round(ZONE2_CEILING * (220 - (age if age else DEFAULT_AGE))))


def session_local_day(session: WorkoutSession) -> Optional[date]:
    """The user's local day for a session (CLAUDE.md local_date rule)."""
    if session.local_date:
        return session.local_date
    derived = derive_local_date(session.date)
    if derived:
        return derived
    return session.date.date() if isinstance(session.date, datetime) else session.date


def set_weight_lb(s: Set) -> float:
    if s.weight_lb is not None:
        return float(s.weight_lb)
    return float(weight_to_lb(s.weight, s.weight_unit) or 0.0)


def working_sets(sets: Sequence[Set]) -> Tuple[Optional[float], List[Set]]:
    """The session's working weight and the sets at it.

    Working weight = the most common weight across non-warm-up sets (0.5 lb
    buckets); ties → heaviest. Returns ``(None, [])`` when nothing counts.
    """
    work = [s for s in sets if not getattr(s, "is_warmup", False) and (s.reps or 0) > 0]
    if not work:
        return None, []
    buckets: Counter = Counter(round(set_weight_lb(s) * 2) / 2 for s in work)
    top = max(buckets.items(), key=lambda kv: (kv[1], kv[0]))[0]
    chosen = [s for s in work if round(set_weight_lb(s) * 2) / 2 == top]
    return float(top), sorted(chosen, key=lambda s: s.set_number or 0)


def _fmt_w(w: Optional[float]) -> str:
    if w is None:
        return "—"
    return f"{w:g}" if float(w).is_integer() else f"{w:.1f}"


def format_last(weight: Optional[float], reps: Sequence[int], rpe: Sequence[Optional[int]] = ()) -> str:
    """``225×5×5`` when uniform, else ``225×5,5,5,4``; ``@ RPE 8`` when logged."""
    if weight is None or not reps:
        return "—"
    if len(set(reps)) == 1 and len(reps) > 1:
        body = f"{_fmt_w(weight)}×{len(reps)}×{reps[0]}"
    else:
        body = f"{_fmt_w(weight)}×{','.join(str(r) for r in reps)}"
    logged = [r for r in rpe if r is not None]
    if logged:
        body += f" @ RPE {max(logged)}"
    return body


# ═══════════════════════════════════════════════════════════════════════════
# History queries (shared with GET /exercises/{id}/last-performance)
# ═══════════════════════════════════════════════════════════════════════════

def family_exercise_ids(db: Session, family_id: str) -> List[str]:
    return [r[0] for r in db.query(Exercise.id).filter(Exercise.family_id == family_id).all()]


def exercise_ids_for_anchor(db: Session, exercise: Exercise) -> Tuple[Optional[str], List[str]]:
    """(family_id, exercise ids) an anchor query should span for an exercise.

    The family when known; else the canonical alias group (spec §15.1).
    """
    if exercise.family_id:
        ids = family_exercise_ids(db, exercise.family_id)
        if exercise.id not in ids:
            ids.append(exercise.id)
        return exercise.family_id, ids
    return None, get_canonical_exercise_ids(db, exercise.id)


@dataclass
class FamilySession:
    session: WorkoutSession
    local_day: date
    sets: List[Set]                      # every set of the family in the session
    exercise_id: Optional[str] = None    # the exercise actually used


def recent_family_sessions(
    db: Session,
    user_id: str,
    exercise_ids: Sequence[str],
    *,
    before: Optional[date] = None,
    since: Optional[date] = None,
    limit: int = 2,
) -> List[FamilySession]:
    """Most recent sessions containing any of ``exercise_ids``, newest first.

    ``before`` is an exclusive local-day upper bound (a hunt on ``D`` anchors
    on sessions with local day < D); ``since`` an inclusive lower bound.
    Filters on ``date`` with a one-day pad in SQL, then on the derived local
    day in Python (NULL ``local_date`` rows fall back per CLAUDE.md).
    """
    if not exercise_ids:
        return []
    containing = (
        db.query(WorkoutExercise.session_id)
        .filter(WorkoutExercise.exercise_id.in_(list(exercise_ids)))
        .subquery()
    )
    query = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets),
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.exercise),
        )
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.id.in_(containing),
        )
    )
    if before is not None:
        query = query.filter(
            WorkoutSession.date < datetime.combine(before + timedelta(days=1), datetime.min.time())
        )
    if since is not None:
        query = query.filter(
            WorkoutSession.date >= datetime.combine(since - timedelta(days=1), datetime.min.time())
        )
    rows = query.order_by(WorkoutSession.date.desc()).all()

    wanted = set(exercise_ids)
    out: List[FamilySession] = []
    for session in rows:
        day = session_local_day(session)
        if day is None:
            continue
        if before is not None and day >= before:
            continue
        if since is not None and day < since:
            continue
        sets: List[Set] = []
        used: Optional[str] = None
        for we in session.workout_exercises:
            if we.exercise_id in wanted:
                sets.extend(we.sets)
                used = used or we.exercise_id
        if not sets:
            continue
        out.append(FamilySession(session=session, local_day=day, sets=sets, exercise_id=used))
        if len(out) >= limit:
            break
    return out


def best_recent_set(
    db: Session,
    user_id: str,
    exercise_ids: Sequence[str],
    *,
    before: Optional[date],
    days: Optional[int] = E1RM_WINDOW_DAYS,
    max_reps: Optional[int] = E1RM_MAX_REPS,
) -> Optional[Tuple[Set, date]]:
    """Best non-warm-up set by e1RM (reps ≤ ``max_reps``) in the window."""
    if not exercise_ids:
        return None
    query = (
        db.query(Set, WorkoutSession)
        .join(WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutExercise.exercise_id.in_(list(exercise_ids)),
            Set.is_warmup == False,  # noqa: E712
            Set.e1rm.isnot(None),
            Set.e1rm > 0,
        )
    )
    if max_reps is not None:
        query = query.filter(Set.reps <= max_reps)
    if before is not None:
        query = query.filter(
            WorkoutSession.date < datetime.combine(before + timedelta(days=1), datetime.min.time())
        )
    if days is not None and before is not None:
        query = query.filter(
            WorkoutSession.date
            >= datetime.combine(before - timedelta(days=days + 1), datetime.min.time())
        )
    best: Optional[Tuple[Set, date]] = None
    for s, session in query.all():
        day = session_local_day(session)
        if day is None:
            continue
        if before is not None and day >= before:
            continue
        if days is not None and before is not None and day < before - timedelta(days=days):
            continue
        if best is None or (s.e1rm or 0) > (best[0].e1rm or 0):
            best = (s, day)
    return best


def last_performance(
    db: Session, user_id: str, exercise: Exercise, *, client_date: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """Spec §15.1 payload for an exercise, or None when never performed.

    Shares :func:`recent_family_sessions` with the anchor so the LogView
    "LAST" column and the prescription never disagree.
    """
    family_id, ids = exercise_ids_for_anchor(db, exercise)
    recent = recent_family_sessions(db, user_id, ids, limit=1)
    if not recent:
        return None
    fs = recent[0]
    today = client_date or date.today()
    sets = sorted(fs.sets, key=lambda s: s.set_number or 0)
    best = best_recent_set(db, user_id, ids, before=None, days=None, max_reps=None)
    return {
        "exercise_id": exercise.id,
        "family_id": family_id,
        "date": fs.local_day.isoformat(),
        "days_ago": max(0, (today - fs.local_day).days),
        "sets": [
            {
                "weight_lb": round(set_weight_lb(s), 1),
                "reps": s.reps,
                "rpe": s.rpe,
                "is_warmup": bool(s.is_warmup),
            }
            for s in sets
        ],
        "best_e1rm": round(best[0].e1rm, 1) if best else None,
        "best_e1rm_date": best[1].isoformat() if best else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Verdicts (§5.1)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Verdict:
    verdict: str                          # progress | hold | deload_lift | e1rm_start | first
    last_weight_lb: Optional[float]
    next_weight_lb: Optional[float]
    target_reps: Tuple[int, int]
    sets_hit: int
    sets_total: int
    reason: str
    last_reps: List[int] = field(default_factory=list)
    last_rpe: List[Optional[int]] = field(default_factory=list)
    last_date: Optional[date] = None
    numbers: Dict[str, Any] = field(default_factory=dict)


def _item_reps(item: Dict[str, Any]) -> Tuple[int, int]:
    reps = item.get("reps") or [5, 5]
    if isinstance(reps, int):
        return int(reps), int(reps)
    lo = int(reps[0])
    hi = int(reps[1]) if len(reps) > 1 else lo
    return lo, max(lo, hi)


def _big_miss(sets: Sequence[Set], target: int) -> bool:
    return sum(1 for s in sets if (target - (s.reps or 0)) >= 2) >= 2


def decide_verdict(
    item: Dict[str, Any],
    last: FamilySession,
    prev: Optional[FamilySession],
    increment: float,
    unit: str = "lb",
    rounding: Optional[float] = None,
) -> Verdict:
    """The progression verdict for the next hunt from the last session.

    ``increment`` is the progression step (the item's, or the Coach's
    override); ``rounding`` the plate granularity (the family's 5 / 2.5 lb),
    defaulting to the step.
    """
    lo, hi = _item_reps(item)
    rounding = rounding or increment
    progression = item.get("progression") or "linear"
    rpe_cap = int(item.get("rpe_cap") or 9)
    weight, work = working_sets(last.sets)
    if weight is None or not work:
        return Verdict("first", None, None, (lo, hi), 0, 0, FIRST_SESSION_TEXT, last_date=last.local_day)

    reps = [int(s.reps or 0) for s in work]
    rpes = [s.rpe for s in work]
    logged_rpe = [r for r in rpes if r is not None]
    base = dict(last_reps=reps, last_rpe=rpes, last_date=last.local_day)

    if progression == "double":
        hit = sum(1 for r in reps if r >= hi)
        if reps and all(r >= hi for r in reps):
            nxt = round_to_increment(weight + increment, rounding, unit)
            return Verdict(
                "progress", weight, nxt, (lo, hi), hit, len(reps),
                f"every set ≥ {hi} → +{increment:g} → {_fmt_w(nxt)}, reps reset to {lo}",
                numbers={"increment_lb": increment, "hi": hi}, **base,
            )
        min_reps = min(reps)
        target_lo = min(hi, min_reps + 1)
        return Verdict(
            "hold", weight, weight, (target_lo, hi), hit, len(reps),
            f"reps {min_reps} → {target_lo} at {_fmt_w(weight)}",
            numbers={"min_reps": min_reps, "target_lo": target_lo}, **base,
        )

    # linear
    target = lo
    shorts = [max(0, target - r) for r in reps]
    hit = sum(1 for s in shorts if s == 0)
    if all(s == 0 for s in shorts):
        if logged_rpe and max(logged_rpe) >= rpe_cap + 2:
            return Verdict(
                "hold", weight, weight, (lo, hi), hit, len(reps),
                f"all sets clean but RPE {max(logged_rpe)} ≥ {rpe_cap + 2} → hold {_fmt_w(weight)}",
                numbers={"rpe_max": max(logged_rpe), "rpe_cap": rpe_cap}, **base,
            )
        nxt = round_to_increment(weight + increment, rounding, unit)
        return Verdict(
            "progress", weight, nxt, (lo, hi), hit, len(reps),
            f"all sets clean → +{increment:g} → {_fmt_w(nxt)}",
            numbers={"increment_lb": increment}, **base,
        )
    if _big_miss(work, target) and prev is not None:
        prev_weight, prev_work = working_sets(prev.sets)
        if prev_work and _big_miss(prev_work, target):
            nxt = round_to_increment(weight * DELOAD_LIFT_FACTOR, rounding, unit)
            return Verdict(
                "deload_lift", weight, nxt, (lo, hi), hit, len(reps),
                f"≥2 sets short by ≥2 reps twice in a row → −10% → {_fmt_w(nxt)}",
                numbers={"factor": DELOAD_LIFT_FACTOR, "prev_date": prev.local_day.isoformat()},
                **base,
            )
    short_sets = sum(1 for s in shorts if s > 0)
    worst = max(shorts)
    return Verdict(
        "hold", weight, weight, (lo, hi), hit, len(reps),
        f"{worst} rep{'s' if worst != 1 else ''} short on {short_sets} set{'s' if short_sets != 1 else ''} → hold {_fmt_w(weight)}",
        numbers={"short_sets": short_sets, "worst_short": worst}, **base,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Prescription object
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Prescription:
    """Engine output. ``to_dict()`` matches ``PrescriptionResponse`` (§15.3)."""
    version: int
    exercises: List[Dict[str, Any]]
    run: Optional[Dict[str, Any]]
    notes: List[str]
    rationale: List[Dict[str, Any]]
    hunt_type: str
    modulation: Optional[Dict[str, Any]]
    guard_flags: List[str]
    system_line: str
    base: Dict[str, Any]                       # un-modulated (what materialization stores)
    base_rationale: List[Dict[str, Any]]
    verdicts: Dict[str, Verdict] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "exercises": copy.deepcopy(self.exercises),
            "run": copy.deepcopy(self.run),
            "notes": list(self.notes),
        }


def _line(key: str, text: str, **numbers: Any) -> Dict[str, Any]:
    return {"key": key, "text": text, "numbers": {k: v for k, v in numbers.items() if v is not None}}


def _profile(db: Session, user_id: str) -> Tuple[Optional[int], Optional[int], str]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        return None, None, "lb"
    unit = "kg" if profile.preferred_unit == WeightUnit.KG else "lb"
    return profile.age, profile.run_hr_cap_bpm, unit


def _family_rows(db: Session, slugs: Iterable[str]) -> Dict[str, ExerciseFamily]:
    slugs = [s for s in set(slugs) if s]
    if not slugs:
        return {}
    return {f.id: f for f in db.query(ExerciseFamily).filter(ExerciseFamily.id.in_(slugs)).all()}


def _canonical_exercise(db: Session, family_id: str, display_name: str) -> Optional[Exercise]:
    """The seeded exercise that best represents a family (name match, else first)."""
    rows = (
        db.query(Exercise)
        .filter(Exercise.family_id == family_id, Exercise.is_custom == False)  # noqa: E712
        .order_by(Exercise.name)
        .all()
    )
    if not rows:
        rows = db.query(Exercise).filter(Exercise.family_id == family_id).order_by(Exercise.name).all()
    if not rows:
        return None
    target = normalize_name(display_name)
    for ex in rows:
        if normalize_name(ex.name) == target:
            return ex
    return rows[0]


def apply_item_overrides(item: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Honor ``overrides["progression"][family]`` and ``overrides["reps"][family]``."""
    item = dict(item)
    fam = item.get("family")
    if not fam:
        return item
    prog = (overrides.get("progression") or {}).get(fam)
    if prog is not None:
        try:
            item["increment_lb"] = float(prog)
        except (TypeError, ValueError):
            pass
    reps = (overrides.get("reps") or {}).get(fam)
    if isinstance(reps, dict):
        if reps.get("sets"):
            item["sets"] = int(reps["sets"])
        if reps.get("reps"):
            r = reps["reps"]
            item["reps"] = [int(r[0]), int(r[-1])] if isinstance(r, (list, tuple)) else [int(r), int(r)]
    return item


def _prescribe_lift(
    db: Session,
    user_id: str,
    item: Dict[str, Any],
    hunt_date: date,
    unit: str,
    families: Dict[str, ExerciseFamily],
    goal_chip: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Verdict]:
    fam_id = item["family"]
    fam = families.get(fam_id)
    display = fam.display_name if fam else FAMILY_DEFS.get(fam_id, {}).get("display_name", fam_id)
    plate = _plate_for(item, families)          # rounding granularity (family)
    increment = _step_for(item, plate)          # progression step (item / override)
    role = item.get("role") or "accessory"
    n_sets = int(item.get("sets") or 3)
    lo, hi = _item_reps(item)
    ids = family_exercise_ids(db, fam_id)
    rationale: List[Dict[str, Any]] = []

    recent = recent_family_sessions(
        db, user_id, ids, before=hunt_date, since=hunt_date - timedelta(days=ANCHOR_WINDOW_DAYS), limit=1
    )
    verdict: Verdict
    if recent:
        last = recent[0]
        prev_rows = recent_family_sessions(db, user_id, ids, before=last.local_day, limit=1)
        verdict = decide_verdict(item, last, prev_rows[0] if prev_rows else None, increment, unit, rounding=plate)
        rationale.append(_line(
            f"anchor:{fam_id}",
            f"{display}: last {last.local_day.strftime('%b %-d')} · "
            f"{format_last(verdict.last_weight_lb, verdict.last_reps, verdict.last_rpe)}",
            date=last.local_day.isoformat(), weight_lb=verdict.last_weight_lb,
            reps=verdict.last_reps, rpe=[r for r in verdict.last_rpe if r is not None] or None,
        ))
        rationale.append(_line(
            f"verdict:{fam_id}", f"{display}: {verdict.reason}",
            verdict=verdict.verdict, next_weight_lb=verdict.next_weight_lb, **verdict.numbers,
        ))
        used_exercise_id = last.exercise_id
    else:
        best = best_recent_set(db, user_id, ids, before=hunt_date)
        if best:
            s, day = best
            pct = pct_for_reps(lo)
            start = round_to_increment((s.e1rm or 0) * pct * E1RM_START_FACTOR, plate, unit)
            verdict = Verdict(
                "e1rm_start", None, start, (lo, hi), 0, 0,
                f"e1RM {s.e1rm:.0f} ({day.strftime('%b %-d')}, {_fmt_w(set_weight_lb(s))}×{s.reps}) × {pct * 100:.0f}% × 0.90 → {_fmt_w(start)}",
                last_date=day,
                numbers={"e1rm": round(s.e1rm or 0, 1), "pct": round(pct, 3), "factor": E1RM_START_FACTOR},
            )
            rationale.append(_line(
                f"anchor:{fam_id}", f"{display}: {verdict.reason}",
                verdict="e1rm_start", next_weight_lb=start, **verdict.numbers,
            ))
        else:
            verdict = Verdict("first", None, None, (lo, hi), 0, 0, FIRST_SESSION_TEXT)
            rationale.append(_line(f"anchor:{fam_id}", f"{display}: {FIRST_SESSION_TEXT}", verdict="first"))
        used_exercise_id = None

    exercise = None
    if used_exercise_id:
        exercise = db.query(Exercise).filter(Exercise.id == used_exercise_id).first()
    if exercise is None:
        exercise = _canonical_exercise(db, fam_id, display)

    weight = verdict.next_weight_lb
    t_lo, t_hi = verdict.target_reps
    sets: List[Dict[str, Any]] = []
    if role == "main" and weight:
        for n, (pct, reps) in enumerate(WARMUP_SCHEME, start=1):
            sets.append({
                "set_number": n,
                "target_weight_lb": round_to_increment(weight * pct, plate, unit),
                "target_reps_lo": reps, "target_reps_hi": reps,
                "target_rpe": None, "is_warmup": True, "is_gate_attempt": False,
            })
        rationale.append(_line(
            f"warmup:{fam_id}",
            f"{display}: warm-ups {' / '.join(_fmt_w(s['target_weight_lb']) for s in sets)} (40/60/80%)",
            weights=[s["target_weight_lb"] for s in sets],
        ))
    for n in range(1, n_sets + 1):
        sets.append({
            "set_number": n,
            "target_weight_lb": weight,
            "target_reps_lo": t_lo, "target_reps_hi": t_hi,
            "target_rpe": float(item["rpe_cap"]) if item.get("rpe_cap") else None,
            "is_warmup": False, "is_gate_attempt": False,
        })

    alternatives: List[str] = []
    for alt in item.get("alternatives") or []:
        alt_fam = families.get(alt)
        alt_ex = _canonical_exercise(db, alt, alt_fam.display_name if alt_fam else alt)
        if alt_ex:
            alternatives.append(alt_ex.id)

    tag = {
        "progress": f"↑ +{increment:g}", "hold": "HOLD", "deload_lift": "↓ −10%",
        "e1rm_start": "e1RM START", "first": "FIRST SESSION",
    }[verdict.verdict]
    exercise_dict = {
        "family_id": fam_id,
        "exercise_id": exercise.id if exercise else None,
        "exercise_name": exercise.name if exercise else display,
        "role": role,
        "alternatives": alternatives,
        "sets": sets,
        "last_performance": (
            format_last(verdict.last_weight_lb, verdict.last_reps, verdict.last_rpe)
            if verdict.last_weight_lb is not None else None
        ),
        "progression_note": f"{tag} · {verdict.reason}",
        "goal": goal_chip,
    }
    return exercise_dict, rationale, verdict


def _run_templates(arc) -> Tuple[int, float]:
    """(number of easy-run templates, total shakeout miles) in an arc's week."""
    easy = 0
    shakeout = 0.0
    for t in arc.templates:
        for it in t.items or []:
            if it.get("run") == "easy":
                easy += 1
            elif it.get("run") == "shakeout":
                m = it.get("miles")
                shakeout += float(m[0]) if isinstance(m, (list, tuple)) else float(m or 0)
    return easy, shakeout


def _prescribe_run(
    db: Session,
    planned_hunt: PlannedHunt,
    item: Dict[str, Any],
    age: Optional[int],
    hr_override: Optional[int],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    from app.services import campaign_service  # lazy: campaign_service imports this module

    campaign = planned_hunt.campaign
    arc = planned_hunt.arc
    kind = item.get("run") or "easy"
    miles_spec = item.get("miles")
    lo = hi = None
    if isinstance(miles_spec, (list, tuple)) and miles_spec:
        lo = float(miles_spec[0])
        hi = float(miles_spec[-1])

    ctx = campaign_service.week_context(campaign, planned_hunt.date)
    target = campaign_service.week_target_miles(db, campaign, planned_hunt.week_start)
    long_run = campaign_service.long_run_miles_for_week(campaign, planned_hunt.week_start) if ctx else None
    n_easy, shakeout_total = _run_templates(arc) if arc else (0, 0.0)

    rationale: List[Dict[str, Any]] = []
    if kind == "long":
        miles = long_run if long_run is not None else (hi or lo or 3.0)
        why = f"long run {miles:.1f} mi: arc {arc.index + 1} ramp toward {arc.long_run_miles:g}" if arc and arc.long_run_miles else f"long run {miles:.1f} mi"
    elif kind == "shakeout":
        miles = lo if lo is not None else 2.0
        why = f"shakeout {miles:.1f} mi (fixed)"
    else:
        if target is not None and n_easy > 0:
            remainder = target - (long_run or 0.0) - shakeout_total
            per = remainder / n_easy
            miles = per
            if lo is not None:
                miles = max(lo, min(hi if hi is not None else per, per))
            why = (
                f"easy {miles:.1f} mi: week {target:.1f} − long {(long_run or 0):.1f}"
                f"{f' − shakeout {shakeout_total:.1f}' if shakeout_total else ''} split over {n_easy}"
                f"{f', clamped to {lo:g}–{hi:g}' if lo is not None else ''}"
            )
        else:
            miles = ((lo or 0) + (hi or lo or 0)) / 2 if lo is not None else 2.0
            why = f"easy {miles:.1f} mi (template range, no arc target)"
    miles = round(max(0.0, miles), 1)
    cap = hr_cap_bpm(age, hr_override)
    rationale.append(_line(
        "run:target", why,
        miles=miles, week_target_miles=target, long_run_miles=long_run,
        campaign_week=(ctx or {}).get("campaign_week"), deload=(ctx or {}).get("deload"),
    ))
    rationale.append(_line(
        "run:hr_cap", f"HR ≤ {cap} bpm (zone-2 ceiling{', your override' if hr_override else f', age {age or DEFAULT_AGE}'})",
        hr_cap_bpm=cap, age=age, override=hr_override,
    ))
    run = {"kind": kind, "miles": miles, "hr_cap_bpm": cap, "note": item.get("note")}
    return run, rationale


def _drop_last_working_set(exercise: Dict[str, Any]) -> bool:
    for i in range(len(exercise["sets"]) - 1, -1, -1):
        s = exercise["sets"][i]
        if not s.get("is_warmup") and not s.get("is_gate_attempt"):
            del exercise["sets"][i]
            return True
    return False


def _scale_working_sets(exercise: Dict[str, Any], factor: float, increment: float, unit: str) -> None:
    for s in exercise["sets"]:
        if s.get("is_warmup") or s.get("is_gate_attempt") or s.get("target_weight_lb") is None:
            continue
        s["target_weight_lb"] = round_to_increment(s["target_weight_lb"] * factor, increment, unit)


def _renumber(exercise: Dict[str, Any]) -> None:
    w = 0
    n = 0
    for s in exercise["sets"]:
        if s.get("is_warmup"):
            w += 1
            s["set_number"] = w
        else:
            n += 1
            s["set_number"] = n


def _latest_load_row(db: Session, user_id: str, on_or_before: date) -> Optional[DailyTrainingLoad]:
    return (
        db.query(DailyTrainingLoad)
        .filter(DailyTrainingLoad.user_id == user_id, DailyTrainingLoad.local_date <= on_or_before)
        .order_by(DailyTrainingLoad.local_date.desc())
        .first()
    )


def _plate_for(item: Dict[str, Any], families: Dict[str, ExerciseFamily]) -> float:
    """Rounding granularity: the family's plate increment (5 barbell / 2.5 dumbbell)."""
    fam = families.get(item.get("family"))
    if fam is not None:
        return float(fam.increment_lb)
    return float(FAMILY_DEFS.get(item.get("family"), {}).get("increment_lb", 5.0))


def _step_for(item: Dict[str, Any], plate: float) -> float:
    """Progression step: the item's ``increment_lb`` (Coach override applied), else the plate."""
    return float(item.get("increment_lb") or plate)


def prescribe(
    db: Session,
    planned_hunt: PlannedHunt,
    *,
    condition: Optional[Dict[str, Any]] = None,
    guard_flags: Sequence[str] = (),
    gate: Optional[PRGate] = None,
) -> Prescription:
    """Concrete targets for a planned hunt (spec §5, §6.4, §10).

    ``condition=None, guard_flags=[], gate=None`` yields the base
    prescription materialization stores; the fetch path passes the live
    values and gets modulation on top (never persisted, except the guard's
    rationale which the caller appends to ``planned_hunts.rationale``).
    """
    template = planned_hunt.template
    campaign = planned_hunt.campaign
    user_id = planned_hunt.user_id
    overrides: Dict[str, Any] = dict(campaign.overrides or {}) if campaign else {}
    age, hr_override, unit = _profile(db, user_id)
    hunt_type = template.type if template else HuntType.REST.value
    guard_flags = [f for f in GUARD_PRIORITY if f in set(guard_flags)]

    raw_items = list((template.items if template else None) or [])
    items = [apply_item_overrides(it, overrides) for it in raw_items]
    slugs = [it.get("family") for it in items if it.get("family")]
    for it in items:
        slugs.extend(it.get("alternatives") or [])
    families = _family_rows(db, slugs)

    goal_chips: Dict[str, Dict[str, Any]] = {}
    if slugs:
        try:
            from app.services import goal_service
            goal_chips = goal_service.strength_goal_chips(db, user_id)
        except Exception:  # pragma: no cover — chips are decoration, never fatal
            goal_chips = {}

    exercises: List[Dict[str, Any]] = []
    rationale: List[Dict[str, Any]] = []
    notes: List[str] = []
    verdicts: Dict[str, Verdict] = {}
    run: Optional[Dict[str, Any]] = None

    for item in items:
        if item.get("family"):
            ex, lines, verdict = _prescribe_lift(
                db, user_id, item, planned_hunt.date, unit, families, goal_chips.get(item["family"])
            )
            exercises.append(ex)
            rationale.extend(lines)
            verdicts[item["family"]] = verdict
        elif item.get("run"):
            run, lines = _prescribe_run(db, planned_hunt, item, age, hr_override)
            rationale.extend(lines)
        elif item.get("note"):
            notes.append(str(item["note"]))
    if template and template.note:
        notes.append(template.note)

    # Explicit lift deload week (apply_deload_now scope lifts|all): main lifts −1 set.
    week_iso = planned_hunt.week_start.isoformat() if planned_hunt.week_start else None
    lift_deload_applied = False
    if week_iso and week_iso in (overrides.get("lift_deload_weeks") or []):
        for ex in exercises:
            if ex["role"] == "main" and _drop_last_working_set(ex):
                _renumber(ex)
                lift_deload_applied = True
        if lift_deload_applied:
            rationale.append(_line("deload:lifts", "Deload week (Coach): main lifts −1 set", week_start=week_iso))

    base = {"version": PRESCRIPTION_VERSION, "exercises": copy.deepcopy(exercises),
            "run": copy.deepcopy(run), "notes": list(notes)}
    base_rationale = copy.deepcopy(rationale)

    # ── Readiness modulation (fetch time) ──
    band = (condition or {}).get("band")
    score = (condition or {}).get("score")
    modulation: Optional[Dict[str, Any]] = None
    if band == BAND_STRAINED:
        for ex in exercises:
            inc = _plate_for(next((i for i in items if i.get("family") == ex["family_id"]), {}), families)
            if ex["role"] == "main":
                _scale_working_sets(ex, STRAINED_MAIN_FACTOR, inc, unit)
            elif ex["role"] == "accessory" and _drop_last_working_set(ex):
                _renumber(ex)
        modulation = {"band": band, "factor": STRAINED_MAIN_FACTOR,
                      "note": f"Condition {score} STRAINED: main lifts ×0.95, last accessory set dropped"}
        rationale.append(_line("modulation", modulation["note"], band=band, score=score, factor=STRAINED_MAIN_FACTOR))
    elif band == BAND_CRITICAL:
        hunt_type = HuntType.LIGHT.value
        for ex in exercises:
            inc = _plate_for(next((i for i in items if i.get("family") == ex["family_id"]), {}), families)
            if ex["role"] == "main":
                _scale_working_sets(ex, CRITICAL_MAIN_FACTOR, inc, unit)
                while sum(1 for s in ex["sets"] if not s.get("is_warmup")) > CRITICAL_MAIN_SETS:
                    _drop_last_working_set(ex)
                _renumber(ex)
        notes.append(REST_OPTION_LINE)
        modulation = {"band": band, "factor": CRITICAL_MAIN_FACTOR,
                      "note": f"Condition {score} CRITICAL: hunt downgraded to light, main lifts ×0.85 for 3 sets — or REST"}
        rationale.append(_line("modulation", modulation["note"], band=band, score=score, factor=CRITICAL_MAIN_FACTOR))
    elif band in (BAND_PEAK, BAND_BATTLE_READY):
        rationale.append(_line("modulation", f"Condition {score} {BAND_LABELS[band]}: no modulation", band=band, score=score))

    # ── Gate attempt (§10.4) ──
    gate_note: Optional[str] = None
    if gate is not None:
        gate_fam = gate.family_id
        target_ex = next((ex for ex in exercises if ex["family_id"] == gate_fam), None)
        if target_ex is None and gate.exercise_id:
            target_ex = next((ex for ex in exercises if ex.get("exercise_id") == gate.exercise_id), None)
        display = target_ex["exercise_name"] if target_ex else (gate.name or "the lift")
        if target_ex is not None and band in (BAND_PEAK, BAND_BATTLE_READY):
            inc = _plate_for(next((i for i in items if i.get("family") == target_ex["family_id"]), {}), families)
            _scale_working_sets(target_ex, GATE_BACKOFF_FACTOR, inc, unit)
            first_working = next((i for i, s in enumerate(target_ex["sets"]) if not s.get("is_warmup")), len(target_ex["sets"]))
            target_ex["sets"].insert(first_working, {
                "set_number": 1, "target_weight_lb": float(gate.target_weight),
                "target_reps_lo": int(gate.target_reps), "target_reps_hi": int(gate.target_reps),
                "target_rpe": None, "is_warmup": False, "is_gate_attempt": True,
            })
            _renumber(target_ex)
            gate_note = f"GATE {_fmt_w(gate.target_weight)}×{gate.target_reps}"
            rationale.append(_line(
                f"gate:{target_ex['family_id']}",
                f"{gate.rank}-rank Gate: {_fmt_w(gate.target_weight)}×{gate.target_reps} as set 1 after warm-ups · working sets −10%",
                gate_id=gate.id, target_weight=gate.target_weight, target_reps=gate.target_reps,
                backoff_factor=GATE_BACKOFF_FACTOR,
            ))
        elif target_ex is not None:
            gate_note = "GATE DEFERRED"
            rationale.append(_line(
                f"gate:{target_ex['family_id']}",
                f"gate attempt deferred to the next {display} hunt (Condition {score} {BAND_LABELS.get(band, band or 'unknown')})",
                gate_id=gate.id, band=band, score=score, deferred=True,
            ))

    # ── Overreach Guard (runs only; deload_due also trims main lifts) ──
    load_row = _latest_load_row(db, user_id, planned_hunt.date) if guard_flags else None
    if run is not None and guard_flags:
        acwr = load_row.run_acwr if load_row else None
        original = run["miles"]
        veto = "run_acwr_critical" in guard_flags or (
            "run_acwr_high" in guard_flags and score is not None and score < GUARD_VETO_CONDITION
        )
        if veto:
            why = (f"run ACWR {acwr:.2f}" if acwr is not None else "run ACWR critical")
            if "run_acwr_critical" not in guard_flags:
                why += f" with Condition {score} < {GUARD_VETO_CONDITION}"
            hunt_type = HuntType.REST.value
            notes.insert(0, f"REST DECREED — {why}. Planned {original:.1f} mi run withdrawn; the plan resumes tomorrow.")
            rationale.append(_line(
                "guard:run_acwr_critical" if "run_acwr_critical" in guard_flags else "guard:run_acwr_high",
                f"REST DECREED: {why} — {original:.1f} mi run withdrawn",
                run_acwr=acwr, condition=score, original_miles=original, cut_miles=0.0,
            ))
            run = None
        else:
            if "run_acwr_high" in guard_flags:
                cut = round(original * ACWR_HIGH_CUT, 1)
                run["miles"] = cut
                run["kind"] = "easy"
                rationale.append(_line(
                    "guard:run_acwr_high",
                    f"Run cut to {cut:.1f} mi and converted to easy: run ACWR {acwr:.2f} > 1.30" if acwr is not None
                    else f"Run cut to {cut:.1f} mi and converted to easy: run ACWR high",
                    run_acwr=acwr, original_miles=original, cut_miles=cut, factor=ACWR_HIGH_CUT,
                ))
            if "ramp_high" in guard_flags:
                if load_row is not None and load_row.miles_plan_7d:
                    allowed = round(max(0.0, RAMP_CAP_FACTOR * load_row.miles_plan_7d - load_row.miles_7d), 1)
                    ahead = (load_row.miles_7d / load_row.miles_plan_7d - 1) * 100
                    if allowed < run["miles"]:
                        before = run["miles"]
                        run["miles"] = allowed
                        rationale.append(_line(
                            "guard:ramp_high",
                            f"Run cut to {allowed:.1f} mi: {ahead:.0f}% ahead of the arc's ramp ({load_row.miles_7d:.1f} of {load_row.miles_plan_7d:.1f} mi planned)",
                            miles_7d=load_row.miles_7d, miles_plan_7d=load_row.miles_plan_7d,
                            original_miles=before, cut_miles=allowed, ahead_pct=round(ahead, 1),
                        ))
                    else:
                        rationale.append(_line(
                            "guard:ramp_high",
                            f"{ahead:.0f}% ahead of the arc's ramp; today's {run['miles']:.1f} mi stays under the 120% cap",
                            miles_7d=load_row.miles_7d, miles_plan_7d=load_row.miles_plan_7d, ahead_pct=round(ahead, 1),
                        ))
                else:
                    rationale.append(_line(
                        "guard:ramp_high", "ramp_high flagged but no 7-day load row — cap skipped", skipped=True,
                    ))
            if "long_run_share" in guard_flags and run["kind"] == "long":
                if load_row is not None and load_row.miles_7d:
                    cap = round(LONG_RUN_SHARE_CAP * load_row.miles_7d, 1)
                    if cap < run["miles"]:
                        before = run["miles"]
                        run["miles"] = cap
                        rationale.append(_line(
                            "guard:long_run_share",
                            f"Long run capped at {cap:.1f} mi: 40% of the last 7 days' {load_row.miles_7d:.1f} mi",
                            miles_7d=load_row.miles_7d, original_miles=before, cut_miles=cap,
                        ))
                else:
                    rationale.append(_line(
                        "guard:long_run_share", "long_run_share flagged but no 7-day load row — cap skipped", skipped=True,
                    ))
            if "deload_due" in guard_flags:
                factor = float(planned_hunt.arc.deload_factor if planned_hunt.arc else 0.75)
                before = run["miles"]
                run["miles"] = round(before * factor, 1)
                rationale.append(_line(
                    "guard:deload_due", f"Deload due: run ×{factor:g} → {run['miles']:.1f} mi",
                    factor=factor, original_miles=before, cut_miles=run["miles"],
                ))
    if "deload_due" in guard_flags and exercises and not lift_deload_applied:
        dropped = []
        for ex in exercises:
            if ex["role"] == "main" and _drop_last_working_set(ex):
                _renumber(ex)
                dropped.append(ex["exercise_name"])
        if dropped:
            rationale.append(_line("guard:deload_due", f"Deload due: −1 set on {', '.join(dropped)}", dropped=dropped))

    system_line = build_system_line(
        hunt_type, exercises, run, verdicts, condition, guard_flags, modulation, gate_note
    )
    return Prescription(
        version=PRESCRIPTION_VERSION, exercises=exercises, run=run, notes=notes,
        rationale=rationale, hunt_type=hunt_type, modulation=modulation,
        guard_flags=guard_flags, system_line=system_line, base=base,
        base_rationale=base_rationale, verdicts=verdicts,
    )


def build_system_line(
    hunt_type: str,
    exercises: List[Dict[str, Any]],
    run: Optional[Dict[str, Any]],
    verdicts: Dict[str, Verdict],
    condition: Optional[Dict[str, Any]],
    guard_flags: Sequence[str],
    modulation: Optional[Dict[str, Any]],
    gate_note: Optional[str] = None,
) -> str:
    """§8.3 System line in the v2 Directive's mono/bracket dialect.

    ``[+5] LAST 225×5×5 · CONDITION 71 BATTLE READY`` — every number comes
    from the engine's own computation.
    """
    parts: List[str] = []
    main = next((ex for ex in exercises if ex["role"] == "main"), None) or (exercises[0] if exercises else None)
    if hunt_type == HuntType.REST.value and run is None and not exercises:
        parts.append("[REST DECREED]")
    elif hunt_type == HuntType.REST.value and run is None:
        parts.append("[REST DECREED]")
    elif main is not None:
        v = verdicts.get(main["family_id"])
        top = next((s for s in reversed(main["sets"]) if not s.get("is_warmup") and not s.get("is_gate_attempt")), None)
        top_w = top["target_weight_lb"] if top else None
        if v is None or v.verdict == "first":
            parts.append(f"[FIRST] {main['exercise_name'].upper()} · NO ANCHOR · RPE 7–8")
        elif v.verdict == "e1rm_start":
            parts.append(f"[START {_fmt_w(top_w)}] e1RM {v.numbers.get('e1rm', 0):.0f} × {v.numbers.get('pct', 0) * 100:.0f}% × 0.90")
        else:
            tag = {"progress": f"+{v.numbers.get('increment_lb', 0):g}", "hold": "HOLD", "deload_lift": "−10%"}[v.verdict]
            parts.append(f"[{tag}] LAST {format_last(v.last_weight_lb, v.last_reps, v.last_rpe)}")
        if modulation is not None and top_w is not None:
            parts.append(f"→ {_fmt_w(top_w)} ×{modulation['factor']:g}")
    elif run is not None:
        parts.append(f"[{run['kind'].upper()} {run['miles']:.1f} MI] HR ≤ {run['hr_cap_bpm']}")
    else:
        parts.append(f"[{hunt_type.upper()}]")
    if condition and condition.get("score") is not None:
        parts.append(f"CONDITION {condition['score']} {BAND_LABELS.get(condition.get('band'), '')}".rstrip())
    if gate_note:
        parts.append(gate_note)
    top_flag = next((f for f in GUARD_PRIORITY if f in guard_flags), None)
    if top_flag:
        parts.append(top_flag.upper().replace("_", " "))
    return " · ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Weekly verdicts for W2 (deload_due) and W3 (debrief candidates)
# ═══════════════════════════════════════════════════════════════════════════

def _default_item(family_id: str, reps: Sequence[int]) -> Dict[str, Any]:
    modal = Counter(reps).most_common(1)[0][0] if reps else 5
    return {
        "family": family_id, "sets": len(reps) or 3, "reps": [modal, modal],
        "role": "accessory", "progression": "linear" if modal <= 6 else "double",
        "increment_lb": FAMILY_DEFS.get(family_id, {}).get("increment_lb", 5.0),
        "rpe_cap": 9,
    }


def progression_verdicts(db: Session, user_id: str, week_start: date) -> List[Dict[str, Any]]:
    """Per family trained in ``[week_start, +6]``: the verdict the engine issues next.

    Rows: ``{family_id, display_name, verdict ∈ progress|hold|deload_lift,
    last_weight_lb, next_weight_lb, increment_lb, sets_hit, sets_total, reason}``.
    Template items come from the active campaign (with overrides); families
    outside the plan get a default item from their modal reps.
    """
    from app.services import campaign_service  # lazy: cycle

    week_end = week_start + timedelta(days=6)
    rows = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets),
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.exercise),
        )
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= datetime.combine(week_start - timedelta(days=1), datetime.min.time()),
            WorkoutSession.date < datetime.combine(week_end + timedelta(days=2), datetime.min.time()),
        )
        .order_by(WorkoutSession.date.desc())
        .all()
    )
    by_family: Dict[str, List[FamilySession]] = defaultdict(list)
    for session in rows:
        day = session_local_day(session)
        if day is None or day < week_start or day > week_end:
            continue
        sets_by_fam: Dict[str, List[Set]] = defaultdict(list)
        ex_by_fam: Dict[str, str] = {}
        for we in session.workout_exercises:
            fam = we.exercise.family_id if we.exercise else None
            if not fam:
                continue
            sets_by_fam[fam].extend(we.sets)
            ex_by_fam.setdefault(fam, we.exercise_id)
        for fam, sets in sets_by_fam.items():
            by_family[fam].append(FamilySession(session, day, sets, ex_by_fam.get(fam)))
    if not by_family:
        return []

    campaign = campaign_service.get_active_campaign(db, user_id)
    overrides = dict(campaign.overrides or {}) if campaign else {}
    plan_items: Dict[str, Dict[str, Any]] = {}
    if campaign:
        ctx = campaign_service.week_context(campaign, week_start)
        arcs = [ctx["arc"]] if ctx else list(campaign.arcs)
        for arc in arcs:
            for t in arc.templates:
                for it in t.items or []:
                    if it.get("family") and it["family"] not in plan_items:
                        plan_items[it["family"]] = apply_item_overrides(it, overrides)

    families = _family_rows(db, by_family.keys())
    _, _, unit = _profile(db, user_id)
    out: List[Dict[str, Any]] = []
    for fam_id, sessions in by_family.items():
        sessions.sort(key=lambda fs: fs.local_day, reverse=True)
        last = sessions[0]
        prev = sessions[1] if len(sessions) > 1 else None
        if prev is None:
            ids = family_exercise_ids(db, fam_id)
            older = recent_family_sessions(db, user_id, ids, before=last.local_day, limit=1)
            prev = older[0] if older else None
        item = plan_items.get(fam_id) or _default_item(
            fam_id, [int(s.reps or 0) for s in last.sets if not s.is_warmup]
        )
        plate = _plate_for(item, families)
        increment = _step_for(item, plate)
        v = decide_verdict(item, last, prev, increment, unit, rounding=plate)
        fam = families.get(fam_id)
        out.append({
            "family_id": fam_id,
            "display_name": fam.display_name if fam else FAMILY_DEFS.get(fam_id, {}).get("display_name", fam_id),
            "verdict": "hold" if v.verdict in ("first", "e1rm_start") else v.verdict,
            "last_weight_lb": v.last_weight_lb,
            "next_weight_lb": v.next_weight_lb,
            "increment_lb": increment,
            "sets_hit": v.sets_hit,
            "sets_total": v.sets_total,
            "reason": v.reason,
            "last_date": v.last_date.isoformat() if v.last_date else None,
        })
    out.sort(key=lambda r: r["display_name"])
    return out


__all__ = [
    "PRESCRIPTION_VERSION",
    "Prescription",
    "Verdict",
    "FamilySession",
    "best_recent_set",
    "build_system_line",
    "decide_verdict",
    "family_exercise_ids",
    "format_last",
    "hr_cap_bpm",
    "last_performance",
    "pct_for_reps",
    "prescribe",
    "progression_verdicts",
    "recent_family_sessions",
    "round_to_increment",
    "session_local_day",
    "set_weight_lb",
    "working_sets",
]
