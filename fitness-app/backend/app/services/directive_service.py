"""
System Directive engine (ARISE v2 spec §5).

Generation: server-side, on the first GET /directive/today of the user's
local day (the client passes ``client_date``). The rule table (§5.2) is
evaluated top-down, first match wins, and the row is persisted so the day's
directive is deterministic.

Completion: auto-detected, no claim button. Workout-driven types (2-7) are
checked from all three ingest paths (POST /workouts, POST /sync, screenshot
save) after the workout lands; the rest directive (type 1) is awarded on
next-day generation. XP flows through award_xp(count_workout=False) — the
same non-workout path quests used.
"""
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.directive import DIRECTIVE_XP_REWARD, DirectiveType, UserDirective
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services.condition_service import (
    BAND_CRITICAL,
    CONDITION_BATTLE_READY_MIN,
    compute_condition,
)
from app.services.cooldown_service import calculate_cooldowns
from app.services.pr_detection import _weight_bucket, get_canonical_exercise_ids
from app.services.quest_service import calculate_todays_workout_stats
from app.services.weekly_report_service import _get_exercise_weekly_sets
from app.services.xp_service import BIG_THREE, award_xp, get_or_create_user_progress

# Rule 3: a muscle counts as "cleared overnight" if its cooldown finished
# within this many hours before generation.
CLEARED_OVERNIGHT_MAX_HOURS = 24.0
# Rule 3: weekly set volume below this fraction of the 4-week mean triggers.
RECLAIM_VOLUME_THRESHOLD = 0.85
# Rule 7 (v2.1): rolling-7-day big-three tonnage below this fraction of the
# 4-week mean triggers the per-lift prescription.
LIFT_LAG_THRESHOLD = 0.85


def _week_windows(client_date: date) -> List[tuple]:
    """Five trailing 7-day windows ending at client_date, newest first.

    Window 0 is the current rolling week ([client_date-6, client_date]);
    windows 1-4 are the four preceding weeks used for the 4-week mean.
    Rolling windows (rather than calendar weeks) keep rule 3 meaningful
    mid-week — a Monday would otherwise compare a 1-day week to full weeks.
    """
    windows = []
    end = client_date
    for _ in range(5):
        start = end - timedelta(days=6)
        windows.append((start, end))
        end = start - timedelta(days=1)
    return windows


def _median_daily_sets(
    db: Session, user_id: str, exercise_ids: List[str], client_date: date
) -> int:
    """Median sets-per-training-day for an exercise group over 4 weeks."""
    window_start = datetime.combine(client_date - timedelta(days=28), datetime.min.time())
    window_end = datetime.combine(client_date, datetime.min.time())
    rows = (
        db.query(WorkoutSession.date, Set.id)
        .join(WorkoutExercise, WorkoutExercise.session_id == WorkoutSession.id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= window_start,
            WorkoutSession.date < window_end,
            WorkoutExercise.exercise_id.in_(exercise_ids),
        )
        .all()
    )
    per_day: Dict[date, int] = {}
    for workout_date, _set_id in rows:
        day = workout_date.date() if hasattr(workout_date, "date") else workout_date
        per_day[day] = per_day.get(day, 0) + 1
    if not per_day:
        return 1
    return max(1, round(statistics.median(per_day.values())))


def _sets_today(
    db: Session, user_id: str, exercise_ids: List[str], target_date: date
) -> List[Set]:
    """All sets logged on target_date for the given exercise-id group."""
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    return (
        db.query(Set)
        .join(WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= day_start,
            WorkoutSession.date < day_end,
            WorkoutExercise.exercise_id.in_(exercise_ids),
        )
        .all()
    )


def _rep_buckets_before(
    db: Session, user_id: str, exercise_ids: List[str], target_date: date
) -> set:
    """(weight_bucket, reps) combos used in the 4 weeks before target_date."""
    window_start = datetime.combine(target_date - timedelta(days=28), datetime.min.time())
    day_start = datetime.combine(target_date, datetime.min.time())
    rows = (
        db.query(Set.weight, Set.reps)
        .join(WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= window_start,
            WorkoutSession.date < day_start,
            WorkoutExercise.exercise_id.in_(exercise_ids),
        )
        .all()
    )
    return {
        (_weight_bucket(weight), reps)
        for weight, reps in rows
        if weight is not None and reps is not None
    }


def _top_lift_for_muscle(muscle_entry: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Most-frequent primary exercise on a cooldown muscle entry."""
    counts: Dict[str, Dict[str, Any]] = {}
    for entry in muscle_entry.get("affected_exercises", []):
        if entry.get("fatigue_type") != "primary":
            continue
        ex_id = entry["exercise_id"]
        if ex_id not in counts:
            counts[ex_id] = {"exercise_id": ex_id,
                             "exercise_name": entry["exercise_name"], "count": 0}
        counts[ex_id]["count"] += 1
    if not counts:
        return None
    top = max(counts.values(), key=lambda c: c["count"])
    return {"exercise_id": top["exercise_id"], "exercise_name": top["exercise_name"]}


def _big_three_exercise_groups(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """The user's big-three lifts as {keyword, name, exercise_ids} groups.

    Groups every exercise the user has ever logged whose name contains a
    BIG_THREE keyword (squat/bench/deadlift variants share a group), the same
    name-matching the plateau rule and gate ranking use.
    """
    from app.models.exercise import Exercise

    rows = (
        db.query(Exercise.id, Exercise.name)
        .join(WorkoutExercise, WorkoutExercise.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
        )
        .distinct()
        .all()
    )
    groups: Dict[str, Dict[str, Any]] = {}
    for exercise_id, name in rows:
        lower = name.lower()
        for keyword in BIG_THREE:
            if keyword in lower:
                group = groups.setdefault(keyword, {
                    "keyword": keyword, "name": name, "exercise_ids": [],
                })
                group["exercise_ids"].append(exercise_id)
                break
    return list(groups.values())


def _volume_lb(
    db: Session, user_id: str, exercise_ids: List[str], start: date, end: date
) -> float:
    """Total tonnage (weight × reps) for an exercise group in [start, end]."""
    day_start = datetime.combine(start, datetime.min.time())
    day_end = datetime.combine(end + timedelta(days=1), datetime.min.time())
    rows = (
        db.query(Set.weight, Set.reps)
        .join(WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= day_start,
            WorkoutSession.date < day_end,
            WorkoutExercise.exercise_id.in_(exercise_ids),
        )
        .all()
    )
    return sum(weight * reps for weight, reps in rows if weight and reps)


def _workouts_this_week(db: Session, user_id: str, client_date: date) -> int:
    """Workouts logged Monday..client_date (calendar week, matches This Week UI)."""
    week_start = client_date - timedelta(days=client_date.weekday())
    day_start = datetime.combine(week_start, datetime.min.time())
    day_end = datetime.combine(client_date + timedelta(days=1), datetime.min.time())
    return (
        db.query(WorkoutSession)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= day_start,
            WorkoutSession.date < day_end,
        )
        .count()
    )


def _finalize_rest_directive(db: Session, user_id: str, client_date: date) -> None:
    """Award yesterday's rest directive if the user actually rested (§5.2-1)."""
    yesterday = client_date - timedelta(days=1)
    directive = (
        db.query(UserDirective)
        .filter(
            UserDirective.user_id == user_id,
            UserDirective.date == yesterday,
            UserDirective.directive_type == DirectiveType.REST.value,
            UserDirective.is_completed.is_(False),
        )
        .first()
    )
    if directive is None:
        return
    stats = calculate_todays_workout_stats(db, user_id, yesterday)
    if stats["workout_count"] == 0:
        directive.is_completed = True
        directive.completed_at = datetime.now(timezone.utc)
        award_xp(db, user_id, directive.xp_reward, count_workout=False)


def _generate(db: Session, user_id: str, client_date: date,
              user_age: Optional[int]) -> UserDirective:
    """Evaluate the §5.2 rule table (first match wins) and build the row."""
    condition = compute_condition(db, user_id, client_date, user_age)
    score = condition["score"]

    directive_type: DirectiveType
    message: str
    params: Dict[str, Any] = {"condition_score": score}

    stats_today = calculate_todays_workout_stats(db, user_id, client_date)

    # ── Rule 1: Condition CRITICAL → rest decreed ──
    if condition["band"] == BAND_CRITICAL:
        directive_type = DirectiveType.REST
        message = f"Rest decreed. Condition {score}. The System forbids the hunt."

    else:
        directive_type = None  # type: ignore[assignment]
        message = ""

        # ── Rule 2: streak lapses today without a workout, Condition ≥ 65 ──
        progress = get_or_create_user_progress(db, user_id)
        last_date = progress.last_workout_date
        if hasattr(last_date, "date"):
            last_date = last_date.date()
        if (
            progress.current_streak >= 1
            and last_date == client_date - timedelta(days=1)
            and stats_today["workout_count"] == 0
            and score >= CONDITION_BATTLE_READY_MIN
        ):
            directive_type = DirectiveType.STREAK_SAVE
            message = "Your streak wavers, Hunter. One hunt keeps the flame."
            params["streak"] = progress.current_streak

        # ── Rule 3: muscle cleared overnight + its top lift's volume is down ──
        if directive_type is None:
            cooldowns = calculate_cooldowns(db, user_id, user_age, include_ready=True)
            cleared = [
                m for m in cooldowns["muscles_cooling"]
                if m.get("status") == "ready"
                and m.get("ready_hours_ago") is not None
                and m["ready_hours_ago"] <= CLEARED_OVERNIGHT_MAX_HOURS
            ]
            windows = _week_windows(client_date)
            for muscle_entry in cleared:
                lift = _top_lift_for_muscle(muscle_entry)
                if lift is None:
                    continue
                exercise_ids = get_canonical_exercise_ids(db, lift["exercise_id"])
                weekly_sets = [
                    sum(
                        count
                        for ex_id, count in _get_exercise_weekly_sets(
                            db, user_id, start, end
                        ).items()
                        if ex_id in exercise_ids
                    )
                    for start, end in windows
                ]
                current, prior = weekly_sets[0], weekly_sets[1:]
                prior_mean = sum(prior) / len(prior)
                if prior_mean > 0 and current < RECLAIM_VOLUME_THRESHOLD * prior_mean:
                    delta_pct = round((1 - current / prior_mean) * 100)
                    muscle = muscle_entry["muscle_group"]
                    directive_type = DirectiveType.RECLAIM_VOLUME
                    message = (
                        f"{muscle.capitalize()} cleared for battle. "
                        f"{lift['exercise_name']} volume down {delta_pct}% — reclaim it."
                    )
                    params.update({
                        "muscle": muscle,
                        "lift": lift["exercise_name"],
                        "exercise_id": lift["exercise_id"],
                        "delta_pct": delta_pct,
                        "target_sets": _median_daily_sets(
                            db, user_id, exercise_ids, client_date
                        ),
                    })
                    break

        # ── Rules 4 & 5 share the insights engine ──
        if directive_type is None:
            # Local import: analytics (api layer) imports services; importing
            # it at module load would risk a cycle as services grow.
            from app.api.analytics import compute_insights
            insights = compute_insights(db, user_id)

            # Rule 4: PLATEAU on a big-three lift
            for insight in insights:
                if insight.type.value != "plateau" or not insight.exercise_name:
                    continue
                name_lower = insight.exercise_name.lower()
                if any(bt in name_lower for bt in BIG_THREE):
                    directive_type = DirectiveType.BREAK_PLATEAU
                    message = (
                        f"{insight.exercise_name} stagnates. "
                        "Break the pattern — new rep range or +5 lb."
                    )
                    params.update({
                        "lift": insight.exercise_name,
                        "exercise_id": insight.exercise_id,
                    })
                    break

            # Rule 5: VOLUME_LOW (frequency < 2/wk)
            if directive_type is None:
                for insight in insights:
                    if insight.type.value == "volume_low":
                        directive_type = DirectiveType.FREQUENCY
                        message = "The System detects idleness. Two hunts this week — minimum."
                        if insight.data and "workouts_per_week" in insight.data:
                            params["workouts_per_week"] = insight.data["workouts_per_week"]
                        break

        # ── Rule 6: open Gate exists ──
        if directive_type is None:
            from app.core.utils import ensure_utc
            from app.services.gate_service import get_live_gates
            gates = get_live_gates(db, user_id)
            if gates:
                gate = gates[0]
                days_left = max(
                    0,
                    (ensure_utc(gate.expires_at) - datetime.now(timezone.utc)).days,
                )
                directive_type = DirectiveType.GATE_REMINDER
                message = f"The Gate waits. {gate.name} closes in {days_left} days."
                params.update({
                    "gate_id": gate.id,
                    "gate_name": gate.name,
                    "exercise_id": gate.exercise_id,
                    "days_left": days_left,
                })

        # ── Rule 7 (v2.1): most-lagging big-three lift by weekly tonnage ──
        # Rolling 7-day tonnage vs the 4-week mean, most-lagging lift wins.
        # Gives the "nothing is wrong" day a concrete order with real numbers
        # instead of the MAINTAIN readout (retro interview, roadmap §9.1).
        if directive_type is None:
            windows = _week_windows(client_date)
            worst: Optional[Dict[str, Any]] = None
            for group in _big_three_exercise_groups(db, user_id):
                weekly = [
                    _volume_lb(db, user_id, group["exercise_ids"], start, end)
                    for start, end in windows
                ]
                current, prior = weekly[0], weekly[1:]
                prior_mean = sum(prior) / len(prior)
                if prior_mean <= 0:
                    continue  # lift not actually in the recent program
                ratio = current / prior_mean
                if ratio >= LIFT_LAG_THRESHOLD:
                    continue
                if worst is None or ratio < worst["ratio"]:
                    worst = {
                        "name": group["name"],
                        "exercise_id": group["exercise_ids"][0],
                        "exercise_ids": group["exercise_ids"],
                        "current": current,
                        "prior_mean": prior_mean,
                        "ratio": ratio,
                    }
            if worst is not None:
                gap = round(worst["prior_mean"] - worst["current"])
                directive_type = DirectiveType.LIFT_LAG
                message = (
                    f"{worst['name']} lags. {round(worst['current']):,} lb moved "
                    f"this week vs {round(worst['prior_mean']):,} lb norm. "
                    f"Close the gap — {gap:,} lb remain."
                )
                params.update({
                    "lift": worst["name"],
                    "exercise_id": worst["exercise_id"],
                    # The full name-matched group the lag was measured on, so
                    # completion counts the same exercises (canonical alias
                    # groups can be narrower than the keyword group).
                    "exercise_ids": worst["exercise_ids"],
                    "volume_7d": round(worst["current"]),
                    "volume_4wk_mean": round(worst["prior_mean"]),
                    "volume_gap_lb": gap,
                })

        # ── Rule 8: default — pace held (status readout, not a goal) ──
        if directive_type is None:
            n = _workouts_this_week(db, user_id, client_date)
            directive_type = DirectiveType.MAINTAIN
            message = (
                f"All systems nominal. {n} "
                f"{'hunt' if n == 1 else 'hunts'} logged this week — hold the line."
            )
            params["hunts_this_week"] = n

    return UserDirective(
        user_id=user_id,
        date=client_date,
        directive_type=directive_type.value,
        message=message,
        params=params,
        xp_reward=DIRECTIVE_XP_REWARD,
    )


def get_or_generate_directive(
    db: Session,
    user_id: str,
    client_date: Optional[date] = None,
    user_age: Optional[int] = None,
) -> UserDirective:
    """Return today's directive, generating (and persisting) it if absent."""
    target_date = client_date or date.today()

    existing = (
        db.query(UserDirective)
        .filter(UserDirective.user_id == user_id, UserDirective.date == target_date)
        .first()
    )
    if existing is not None:
        return existing

    # First generation of the local day: settle yesterday's rest directive.
    _finalize_rest_directive(db, user_id, target_date)

    directive = _generate(db, user_id, target_date, user_age)
    db.add(directive)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent first-request race on (user_id, date): the other request
        # won — return its row.
        db.rollback()
        directive = (
            db.query(UserDirective)
            .filter(UserDirective.user_id == user_id, UserDirective.date == target_date)
            .first()
        )
    db.refresh(directive)
    return directive


def get_directive_history(db: Session, user_id: str, limit: int = 7) -> List[UserDirective]:
    """Most recent directives, newest first."""
    return (
        db.query(UserDirective)
        .filter(UserDirective.user_id == user_id)
        .order_by(UserDirective.date.desc())
        .limit(limit)
        .all()
    )


def check_directive_completion(
    db: Session, user_id: str, workout_date: date
) -> Optional[Dict[str, Any]]:
    """Auto-detect directive completion after a workout lands (§5.2 types 2-7).

    Called from all three ingest paths (POST /workouts, POST /sync, screenshot
    save) after the workout's sets are flushed. Idempotent: a completed
    directive is never re-awarded. Returns the award_xp result when the
    directive completed, else None.
    """
    if hasattr(workout_date, "date"):
        workout_date = workout_date.date()

    directive = (
        db.query(UserDirective)
        .filter(UserDirective.user_id == user_id, UserDirective.date == workout_date)
        .first()
    )
    if directive is None or directive.is_completed:
        return None

    dtype = directive.directive_type
    params = directive.params or {}
    completed = False

    if dtype in (
        DirectiveType.STREAK_SAVE.value,
        DirectiveType.FREQUENCY.value,
        DirectiveType.MAINTAIN.value,
    ):
        # Any workout logged that local day completes these.
        completed = True

    elif dtype == DirectiveType.RECLAIM_VOLUME.value:
        exercise_id = params.get("exercise_id")
        target_sets = params.get("target_sets", 1)
        if exercise_id:
            exercise_ids = get_canonical_exercise_ids(db, exercise_id)
            completed = len(_sets_today(db, user_id, exercise_ids, workout_date)) >= target_sets

    elif dtype == DirectiveType.BREAK_PLATEAU.value:
        exercise_id = params.get("exercise_id")
        if exercise_id:
            exercise_ids = get_canonical_exercise_ids(db, exercise_id)
            prior_buckets = _rep_buckets_before(db, user_id, exercise_ids, workout_date)
            completed = any(
                (_weight_bucket(s.weight), s.reps) not in prior_buckets
                for s in _sets_today(db, user_id, exercise_ids, workout_date)
                if s.weight is not None and s.reps is not None
            )

    elif dtype == DirectiveType.GATE_REMINDER.value:
        # "Gate cleared or attempted" — any set on that lift today (§5.2-6).
        exercise_id = params.get("exercise_id")
        if exercise_id:
            exercise_ids = get_canonical_exercise_ids(db, exercise_id)
            completed = len(_sets_today(db, user_id, exercise_ids, workout_date)) > 0

    elif dtype == DirectiveType.LIFT_LAG.value:
        # The order was "close the gap" — completed when today's tonnage on
        # that lift covers the gap frozen at generation time, counted over the
        # same name-matched group the rule measured the lag on.
        exercise_ids = params.get("exercise_ids") or (
            get_canonical_exercise_ids(db, params["exercise_id"])
            if params.get("exercise_id") else []
        )
        gap = params.get("volume_gap_lb", 0)
        if exercise_ids:
            tonnage = sum(
                s.weight * s.reps
                for s in _sets_today(db, user_id, exercise_ids, workout_date)
                if s.weight is not None and s.reps is not None
            )
            completed = tonnage >= gap

    # DirectiveType.REST: a workout can never complete it (awarded next-day
    # by _finalize_rest_directive when the user actually rested).

    if not completed:
        return None

    directive.is_completed = True
    directive.completed_at = datetime.now(timezone.utc)
    return award_xp(db, user_id, directive.xp_reward, count_workout=False)
