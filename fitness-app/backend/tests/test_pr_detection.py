"""
Tests for pr_detection.detect_and_create_prs and canonical alias handling.

Covers:
- e1RM PR on first set for a new exercise
- Tie on e1RM does NOT create a new PR (strict > comparison)
- Strict e1RM PR (new best 1RM beats previous best)
- Rep PR at a fixed weight
- Tie on rep PR (same reps at same weight) does NOT create a new PR
- Canonical aliases (Back Squat / Squat) share PR history
- Multiple sets within a single detection call advance the rolling max
- Floating-point weight rounding (222.5 vs 222.4 rounds into same bucket)
"""
from datetime import datetime, timezone

import pytest

from app.core.e1rm import calculate_e1rm
from app.models.exercise import Exercise
from app.models.pr import PR, PRType
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession
from app.services.pr_detection import (
    check_first_time_exercise,
    detect_and_create_prs,
    get_canonical_exercise_ids,
)


def _mk_exercise(db, name: str, canonical_id: str = None, category: str = "Push") -> Exercise:
    ex = Exercise(name=name, canonical_id=canonical_id, category=category)
    db.add(ex)
    db.flush()
    return ex


def _mk_workout(db, user_id: str, exercise: Exercise) -> WorkoutExercise:
    session = WorkoutSession(user_id=user_id, date=datetime.now(timezone.utc))
    db.add(session)
    db.flush()
    we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    return we


def _mk_set(db, we: WorkoutExercise, weight: float, reps: int, set_number: int = 1) -> Set:
    s = Set(
        workout_exercise_id=we.id,
        weight=weight,
        weight_unit=WeightUnit.LB,
        reps=reps,
        set_number=set_number,
        e1rm=round(calculate_e1rm(weight, reps, "epley"), 2),
    )
    db.add(s)
    db.flush()
    return s


class TestFirstTimeExercise:
    def test_no_prior_prs_is_first_time(self, db, create_test_user):
        user, _ = create_test_user(email="ft1@example.com")
        ex = _mk_exercise(db, "Bench Press")
        db.commit()
        assert check_first_time_exercise(db, user.id, ex.id) is True

    def test_prior_pr_is_not_first_time(self, db, create_test_user):
        user, _ = create_test_user(email="ft2@example.com")
        ex = _mk_exercise(db, "Bench Press")
        we = _mk_workout(db, user.id, ex)
        s = _mk_set(db, we, 225, 1)
        db.add(PR(
            user_id=user.id, exercise_id=ex.id, set_id=s.id,
            pr_type=PRType.E1RM, value=225.0,
            achieved_at=datetime.now(timezone.utc),
        ))
        db.commit()
        assert check_first_time_exercise(db, user.id, ex.id) is False


class TestCanonicalAliases:
    def test_canonical_ids_returns_all_aliases(self, db):
        # Simulate "Squat" (canonical) and "Back Squat" (alias) sharing canonical_id
        canonical = "squat-canon-1"
        squat = _mk_exercise(db, "Squat", canonical_id=canonical)
        back_squat = _mk_exercise(db, "Back Squat", canonical_id=canonical)
        _mk_exercise(db, "Leg Press")  # different exercise, no shared canonical
        db.commit()

        ids = set(get_canonical_exercise_ids(db, squat.id))
        assert squat.id in ids
        assert back_squat.id in ids
        assert len(ids) == 2

    def test_exercise_without_canonical_id_returns_self(self, db):
        ex = _mk_exercise(db, "Lone Exercise", canonical_id=None)
        db.commit()
        assert get_canonical_exercise_ids(db, ex.id) == [ex.id]

    def test_pr_on_alias_blocks_pr_on_canonical(self, db, create_test_user):
        """If user sets a 300-lb PR on "Back Squat", a 250-lb lift on "Squat"
        should not count as an e1RM PR."""
        user, _ = create_test_user(email="alias@example.com")
        canonical = "squat-canon-2"
        back_squat = _mk_exercise(db, "Back Squat", canonical_id=canonical)
        squat = _mk_exercise(db, "Squat", canonical_id=canonical)
        db.commit()

        # First workout: 300 lb single on Back Squat
        we1 = _mk_workout(db, user.id, back_squat)
        s1 = _mk_set(db, we1, 300, 1)
        prs1 = detect_and_create_prs(db, user.id, we1, [s1])
        db.commit()
        assert len(prs1) >= 1
        assert any(p.pr_type == PRType.E1RM for p in prs1)

        # Second workout: 250 lb single on "Squat" — lower e1RM, no new PR
        we2 = _mk_workout(db, user.id, squat)
        s2 = _mk_set(db, we2, 250, 1)
        prs2 = detect_and_create_prs(db, user.id, we2, [s2])
        db.commit()
        e1rm_prs = [p for p in prs2 if p.pr_type == PRType.E1RM]
        assert e1rm_prs == []


class TestE1RMPR:
    def test_first_set_creates_e1rm_pr(self, db, create_test_user):
        user, _ = create_test_user(email="e1rm1@example.com")
        ex = _mk_exercise(db, "Deadlift")
        we = _mk_workout(db, user.id, ex)
        s = _mk_set(db, we, 315, 1)
        prs = detect_and_create_prs(db, user.id, we, [s])
        db.commit()

        e1rm_prs = [p for p in prs if p.pr_type == PRType.E1RM]
        assert len(e1rm_prs) == 1
        assert e1rm_prs[0].value == pytest.approx(s.e1rm, rel=1e-6)

    def test_strict_e1rm_pr_requires_new_best(self, db, create_test_user):
        user, _ = create_test_user(email="e1rm2@example.com")
        ex = _mk_exercise(db, "Deadlift")

        # First PR
        we1 = _mk_workout(db, user.id, ex)
        s1 = _mk_set(db, we1, 315, 1)  # e1RM = 315
        detect_and_create_prs(db, user.id, we1, [s1])
        db.commit()

        # Lower lift — no PR
        we2 = _mk_workout(db, user.id, ex)
        s2 = _mk_set(db, we2, 275, 1)  # e1RM = 275
        prs2 = detect_and_create_prs(db, user.id, we2, [s2])
        db.commit()
        assert [p for p in prs2 if p.pr_type == PRType.E1RM] == []

        # Higher lift — new PR
        we3 = _mk_workout(db, user.id, ex)
        s3 = _mk_set(db, we3, 365, 1)  # e1RM = 365
        prs3 = detect_and_create_prs(db, user.id, we3, [s3])
        db.commit()
        e1rm_prs = [p for p in prs3 if p.pr_type == PRType.E1RM]
        assert len(e1rm_prs) == 1
        assert e1rm_prs[0].value == pytest.approx(365.0, rel=1e-6)

    def test_e1rm_tie_does_not_create_new_pr(self, db, create_test_user):
        """Hitting the exact same e1RM as the existing best must not create a PR."""
        user, _ = create_test_user(email="tie@example.com")
        ex = _mk_exercise(db, "Deadlift")

        we1 = _mk_workout(db, user.id, ex)
        s1 = _mk_set(db, we1, 315, 1)  # e1RM = 315.0
        detect_and_create_prs(db, user.id, we1, [s1])
        db.commit()

        # Tie attempt: same 315x1
        we2 = _mk_workout(db, user.id, ex)
        s2 = _mk_set(db, we2, 315, 1)
        prs2 = detect_and_create_prs(db, user.id, we2, [s2])
        db.commit()

        assert [p for p in prs2 if p.pr_type == PRType.E1RM] == []

    def test_multiple_sets_advance_rolling_max(self, db, create_test_user):
        """Within one detection call, the rolling max must advance strictly;
        sets that don't beat the current best do NOT create an e1RM PR."""
        user, _ = create_test_user(email="roll@example.com")
        ex = _mk_exercise(db, "Bench Press")
        we = _mk_workout(db, user.id, ex)
        # Epley: 185x3 = 203.5, 205x3 = 225.5, 225x1 = 225.0
        # So set 3's e1RM (225) is LESS than set 2's (225.5) — no new e1RM PR.
        sets = [
            _mk_set(db, we, 185, 3, set_number=1),  # e1RM 203.5, new PR
            _mk_set(db, we, 205, 3, set_number=2),  # e1RM 225.5, new PR
            _mk_set(db, we, 225, 1, set_number=3),  # e1RM 225.0, NOT a PR
        ]
        prs = detect_and_create_prs(db, user.id, we, sets)
        db.commit()
        e1rm_prs = [p for p in prs if p.pr_type == PRType.E1RM]
        assert len(e1rm_prs) == 2

        # But all three sets are at new weight buckets, so each is a rep PR.
        rep_prs = [p for p in prs if p.pr_type == PRType.REP_PR]
        assert len(rep_prs) == 3


class TestRepPR:
    def test_first_rep_at_weight_creates_rep_pr(self, db, create_test_user):
        user, _ = create_test_user(email="rep1@example.com")
        ex = _mk_exercise(db, "Bench Press")
        we = _mk_workout(db, user.id, ex)
        s = _mk_set(db, we, 185, 5)
        prs = detect_and_create_prs(db, user.id, we, [s])
        db.commit()

        rep_prs = [p for p in prs if p.pr_type == PRType.REP_PR]
        assert len(rep_prs) == 1
        assert rep_prs[0].weight == pytest.approx(185.0)
        assert rep_prs[0].reps == 5

    def test_rep_pr_tie_does_not_create_pr(self, db, create_test_user):
        """Hitting the same reps at the same weight is not a new rep PR."""
        user, _ = create_test_user(email="rep2@example.com")
        ex = _mk_exercise(db, "Bench Press")

        # First: 185 x 5
        we1 = _mk_workout(db, user.id, ex)
        s1 = _mk_set(db, we1, 185, 5)
        detect_and_create_prs(db, user.id, we1, [s1])
        db.commit()

        # Tie: 185 x 5 again — no PR
        we2 = _mk_workout(db, user.id, ex)
        s2 = _mk_set(db, we2, 185, 5)
        prs2 = detect_and_create_prs(db, user.id, we2, [s2])
        db.commit()

        rep_prs = [p for p in prs2 if p.pr_type == PRType.REP_PR]
        assert rep_prs == []

    def test_rep_pr_more_reps_at_same_weight(self, db, create_test_user):
        """More reps at the same weight beats the previous rep PR."""
        user, _ = create_test_user(email="rep3@example.com")
        ex = _mk_exercise(db, "Bench Press")

        we1 = _mk_workout(db, user.id, ex)
        s1 = _mk_set(db, we1, 185, 5)
        detect_and_create_prs(db, user.id, we1, [s1])
        db.commit()

        we2 = _mk_workout(db, user.id, ex)
        s2 = _mk_set(db, we2, 185, 8)  # more reps
        prs2 = detect_and_create_prs(db, user.id, we2, [s2])
        db.commit()

        rep_prs = [p for p in prs2 if p.pr_type == PRType.REP_PR]
        assert len(rep_prs) == 1
        assert rep_prs[0].reps == 8

    def test_rolling_rep_pr_within_call_dedupes_by_bucket(self, db, create_test_user):
        """Inside a single detect_and_create_prs call, two sets at floating-point
        weights that round into the same half-pound bucket should not both PR
        if reps don't increase."""
        user, _ = create_test_user(email="float@example.com")
        ex = _mk_exercise(db, "Squat")
        we = _mk_workout(db, user.id, ex)

        # Both sets round to the 222.5 bucket; same reps means second is not a PR.
        sets = [
            _mk_set(db, we, 222.3, 5, set_number=1),
            _mk_set(db, we, 222.6, 5, set_number=2),
        ]
        prs = detect_and_create_prs(db, user.id, we, sets)
        db.commit()

        rep_prs = [p for p in prs if p.pr_type == PRType.REP_PR]
        # Only the first set produced a rep PR — the rolling rep_pr_map blocks
        # the second from tying at the same rounded bucket.
        assert len(rep_prs) == 1

    def test_known_bug_cross_call_weight_rounding_not_deduplicated(self, db, create_test_user):
        """Document current behavior: between calls, rep PRs are stored at the raw
        weight, but compared at the rounded weight_key. This means a 222.3 lb x 5
        stored PR will not block a 222.6 lb x 5 tie in a later workout.

        This test pins the current (buggy) behavior so a future fix intentionally
        breaks this test rather than silently changing it.
        """
        user, _ = create_test_user(email="floatbug@example.com")
        ex = _mk_exercise(db, "Squat")

        we1 = _mk_workout(db, user.id, ex)
        s1 = _mk_set(db, we1, 222.3, 5)
        detect_and_create_prs(db, user.id, we1, [s1])
        db.commit()

        we2 = _mk_workout(db, user.id, ex)
        s2 = _mk_set(db, we2, 222.6, 5)  # Would round to same 222.5 bucket
        prs2 = detect_and_create_prs(db, user.id, we2, [s2])
        db.commit()

        # Current behavior: the 222.6 tie IS logged as a "new" rep PR because
        # the stored map key (222.3) doesn't match the lookup key (222.5).
        rep_prs = [p for p in prs2 if p.pr_type == PRType.REP_PR]
        assert len(rep_prs) == 1, (
            "If this assertion flips to 0, the raw-weight vs rounded-bucket "
            "inconsistency has been fixed — update both this test and the "
            "PR detection cross-workout rounding logic."
        )


class TestMixedPRs:
    def test_single_set_can_create_both_e1rm_and_rep_pr(self, db, create_test_user):
        """A first-ever set always creates both an e1RM PR and a rep PR."""
        user, _ = create_test_user(email="mixed@example.com")
        ex = _mk_exercise(db, "Overhead Press")
        we = _mk_workout(db, user.id, ex)
        s = _mk_set(db, we, 135, 3)
        prs = detect_and_create_prs(db, user.id, we, [s])
        db.commit()

        assert any(p.pr_type == PRType.E1RM for p in prs)
        assert any(p.pr_type == PRType.REP_PR for p in prs)
