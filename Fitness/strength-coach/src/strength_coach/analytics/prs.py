"""Personal record (PR) detection and tracking."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from ..models import ExercisePerformance, SetRecord, WorkoutSession
from .e1rm import estimate_e1rm, is_reliable_estimate


@dataclass
class PRRecord:
    """A personal record entry."""

    exercise_id: str
    pr_type: str  # "e1rm", "rep_pr_1", "rep_pr_3", "rep_pr_5", etc.
    value: Decimal
    date: date
    previous_value: Optional[Decimal] = None
    improvement_pct: Optional[float] = None
    weight: Optional[Decimal] = None
    reps: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "pr_type": self.pr_type,
            "value": float(self.value),
            "date": self.date.isoformat(),
            "previous_value": float(self.previous_value) if self.previous_value else None,
            "improvement_pct": self.improvement_pct,
            "weight": float(self.weight) if self.weight else None,
            "reps": self.reps,
        }


# Rep ranges for rep PRs
REP_PR_THRESHOLDS = [1, 3, 5, 8, 10]


def detect_set_prs(
    set_record: SetRecord,
    exercise_id: str,
    session_date: date,
    historical_prs: dict[str, PRRecord],
) -> list[PRRecord]:
    """
    Detect PRs from a single set.

    Args:
        set_record: The set to check
        exercise_id: Canonical exercise ID
        session_date: Date of the session
        historical_prs: Current PR records for this exercise

    Returns:
        List of new PRs detected
    """
    new_prs: list[PRRecord] = []

    if set_record.is_warmup:
        return new_prs

    weight_lb = set_record.weight_lb
    reps = set_record.reps

    # Check e1RM PR (only for reliable rep ranges)
    if is_reliable_estimate(reps):
        e1rm = estimate_e1rm(weight_lb, reps)
        e1rm_key = "e1rm"

        if e1rm > Decimal("0"):
            current_e1rm_pr = historical_prs.get(e1rm_key)

            if current_e1rm_pr is None or e1rm > current_e1rm_pr.value:
                improvement = None
                if current_e1rm_pr:
                    improvement = float((e1rm - current_e1rm_pr.value) / current_e1rm_pr.value * 100)

                new_prs.append(
                    PRRecord(
                        exercise_id=exercise_id,
                        pr_type=e1rm_key,
                        value=e1rm,
                        date=session_date,
                        previous_value=current_e1rm_pr.value if current_e1rm_pr else None,
                        improvement_pct=improvement,
                        weight=weight_lb,
                        reps=reps,
                    )
                )

    # Check rep PRs (best weight at specific rep count)
    for threshold in REP_PR_THRESHOLDS:
        if reps >= threshold:
            rep_key = f"rep_pr_{threshold}"
            current_rep_pr = historical_prs.get(rep_key)

            if current_rep_pr is None or weight_lb > current_rep_pr.value:
                improvement = None
                if current_rep_pr:
                    improvement = float(
                        (weight_lb - current_rep_pr.value) / current_rep_pr.value * 100
                    )

                new_prs.append(
                    PRRecord(
                        exercise_id=exercise_id,
                        pr_type=rep_key,
                        value=weight_lb,
                        date=session_date,
                        previous_value=current_rep_pr.value if current_rep_pr else None,
                        improvement_pct=improvement,
                        weight=weight_lb,
                        reps=reps,
                    )
                )

    return new_prs


def detect_exercise_prs(
    performance: ExercisePerformance,
    session_date: date,
    historical_prs: dict[str, PRRecord],
) -> list[PRRecord]:
    """
    Detect all PRs from an exercise performance.

    Args:
        performance: The exercise with all sets
        session_date: Date of the session
        historical_prs: Current PRs for this exercise

    Returns:
        List of new PRs (only the best for each PR type)
    """
    exercise_id = performance.canonical_id or performance.exercise_name.lower()
    all_prs: dict[str, PRRecord] = {}

    for set_record in performance.working_sets:
        set_prs = detect_set_prs(set_record, exercise_id, session_date, historical_prs)

        for pr in set_prs:
            existing = all_prs.get(pr.pr_type)
            if existing is None or pr.value > existing.value:
                all_prs[pr.pr_type] = pr

    return list(all_prs.values())


def detect_session_prs(
    session: WorkoutSession,
    all_historical_prs: dict[str, dict[str, PRRecord]],
) -> list[PRRecord]:
    """
    Detect all PRs from a workout session.

    Args:
        session: The workout session
        all_historical_prs: Dict mapping exercise_id to its PR dict

    Returns:
        List of all new PRs from this session
    """
    all_new_prs: list[PRRecord] = []

    for exercise in session.exercises:
        exercise_id = exercise.canonical_id or exercise.exercise_name.lower()
        historical = all_historical_prs.get(exercise_id, {})

        exercise_prs = detect_exercise_prs(exercise, session.date, historical)
        all_new_prs.extend(exercise_prs)

    return all_new_prs


def build_pr_history(
    sets_data: list[dict],
    exercise_id: str,
) -> dict[str, PRRecord]:
    """
    Build current PR records from historical set data.

    Args:
        sets_data: Historical sets from storage
        exercise_id: Canonical exercise ID

    Returns:
        Dict mapping pr_type to current PRRecord
    """
    prs: dict[str, PRRecord] = {}

    for set_data in sets_data:
        if set_data.get("is_warmup"):
            continue

        weight = Decimal(str(set_data["weight_lb"]))
        reps = int(set_data["reps"])
        set_date = date.fromisoformat(set_data["session_date"])

        # e1RM
        if is_reliable_estimate(reps):
            e1rm = estimate_e1rm(weight, reps)
            if e1rm > Decimal("0"):
                if "e1rm" not in prs or e1rm > prs["e1rm"].value:
                    prs["e1rm"] = PRRecord(
                        exercise_id=exercise_id,
                        pr_type="e1rm",
                        value=e1rm,
                        date=set_date,
                        weight=weight,
                        reps=reps,
                    )

        # Rep PRs
        for threshold in REP_PR_THRESHOLDS:
            if reps >= threshold:
                key = f"rep_pr_{threshold}"
                if key not in prs or weight > prs[key].value:
                    prs[key] = PRRecord(
                        exercise_id=exercise_id,
                        pr_type=key,
                        value=weight,
                        date=set_date,
                        weight=weight,
                        reps=reps,
                    )

    return prs


def format_pr_for_display(pr: PRRecord) -> str:
    """Format a PR for human-readable display."""
    if pr.pr_type == "e1rm":
        base = f"e1RM: {pr.value} lb"
        if pr.weight and pr.reps:
            base += f" (from {pr.weight} lb x {pr.reps})"
    else:
        # rep_pr_X format
        threshold = pr.pr_type.replace("rep_pr_", "")
        base = f"{threshold}+ rep PR: {pr.value} lb x {pr.reps}"

    if pr.improvement_pct:
        base += f" (+{pr.improvement_pct:.1f}%)"

    return base
