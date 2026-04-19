"""
Tests for achievement_service.check_and_unlock_achievements and related flows.

Covers:
- workout_count unlock thresholds
- pr_count unlock thresholds
- streak_days unlock thresholds
- level_reached unlocks
- rank_reached progression (E -> D -> C -> B -> A -> S)
- weight_lifted (exercise-specific)
- Idempotent unlocks (already-unlocked achievements are skipped)
- XP reward is applied to UserProgress.total_xp
"""
import pytest

from app.models.achievement import AchievementDefinition, UserAchievement
from app.models.progress import UserProgress
from app.services.achievement_service import (
    check_and_unlock_achievements,
    get_recently_unlocked,
    get_user_achievements,
    seed_achievement_definitions,
    unlock_achievement,
)
from app.services.xp_service import get_or_create_user_progress


@pytest.fixture
def seeded_db(db):
    """DB with achievement definitions seeded."""
    seed_achievement_definitions(db)
    db.commit()
    return db


class TestWorkoutCountUnlocks:
    def test_first_workout_unlocks_first_steps(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="wc1@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"workout_count": 1}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "First Steps" in names

    def test_10_workouts_unlocks_first_steps_and_dedicated(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="wc10@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"workout_count": 10}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "First Steps" in names
        assert "Dedicated" in names
        assert "Committed" not in names  # requires 25

    def test_workout_count_below_threshold_unlocks_nothing_new(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="wc0@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"workout_count": 0}
        )
        # no workout_count achievements have requirement 0
        names = {a["name"] for a in unlocked}
        assert "First Steps" not in names


class TestPRCountUnlocks:
    def test_first_pr_unlocks_breaking_limits(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="pr1@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"prs_count": 1}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "Breaking Limits" in names

    def test_10_prs_unlocks_record_breaker(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="pr10@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"prs_count": 10}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "Breaking Limits" in names
        assert "Record Breaker" in names


class TestStreakUnlocks:
    def test_7_day_streak_unlocks_7_day_warrior(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="st7@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"current_streak": 7}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "7-Day Warrior" in names
        assert "Fortnight Fighter" not in names

    def test_30_day_streak_unlocks_all_streaks(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="st30@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"current_streak": 30}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "7-Day Warrior" in names
        assert "Fortnight Fighter" in names
        assert "30-Day Legend" in names


class TestLevelAndRankUnlocks:
    def test_level_10_unlocks_rising_hunter(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="lvl10@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"level": 10}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "Rising Hunter" in names

    def test_rank_progression_e_to_s(self, seeded_db, create_test_user):
        """Each rank step unlocks exactly the achievements that are cumulatively unlocked."""
        user, _ = create_test_user(email="rankprog@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        # E -> D
        newly = check_and_unlock_achievements(seeded_db, user.id, {"rank": "D"})
        seeded_db.commit()
        assert "D-Rank Hunter" in {a["name"] for a in newly}

        # D -> C
        newly = check_and_unlock_achievements(seeded_db, user.id, {"rank": "C"})
        seeded_db.commit()
        names = {a["name"] for a in newly}
        assert "C-Rank Hunter" in names
        assert "D-Rank Hunter" not in names  # already unlocked

        # Jump to S
        newly = check_and_unlock_achievements(seeded_db, user.id, {"rank": "S"})
        seeded_db.commit()
        names = {a["name"] for a in newly}
        assert {"B-Rank Hunter", "A-Rank Hunter", "S-Rank Hunter"}.issubset(names)


class TestExerciseSpecificUnlocks:
    def test_bench_225_unlocks_bench_tier_chain(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="bench@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"exercise_prs": {"bench press": 225}}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "Iron Initiate" in names    # 135
        assert "Bench Warrior" in names    # 185
        assert "Bench Baron" in names      # 225

    def test_wrong_exercise_name_does_not_unlock(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="wrongex@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        # exercise_prs keyed with a name that does not match any achievement
        unlocked = check_and_unlock_achievements(
            seeded_db, user.id, {"exercise_prs": {"lateral raise": 500}}
        )
        seeded_db.commit()

        names = {a["name"] for a in unlocked}
        assert "Iron Initiate" not in names
        assert "Squat Starter" not in names


class TestIdempotencyAndXP:
    def test_achievement_xp_reward_applied(self, seeded_db, create_test_user):
        """Unlocking an achievement awards its xp_reward to UserProgress."""
        user, _ = create_test_user(email="xp@example.com")
        progress = get_or_create_user_progress(seeded_db, user.id)
        progress.total_xp = 0
        seeded_db.commit()

        result = unlock_achievement(seeded_db, user.id, "first_workout")
        seeded_db.commit()

        assert result is not None
        assert result["name"] == "First Steps"

        progress = seeded_db.query(UserProgress).filter_by(user_id=user.id).first()
        # First Steps awards 50 XP
        assert progress.total_xp == 50

    def test_double_unlock_is_idempotent(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="dup@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        r1 = unlock_achievement(seeded_db, user.id, "first_workout")
        seeded_db.commit()
        r2 = unlock_achievement(seeded_db, user.id, "first_workout")
        seeded_db.commit()

        assert r1 is not None
        assert r2 is None  # second call returns None

        # Verify only one unlock row exists
        count = seeded_db.query(UserAchievement).filter_by(
            user_id=user.id, achievement_id="first_workout"
        ).count()
        assert count == 1

    def test_check_does_not_re_unlock(self, seeded_db, create_test_user):
        """Repeated check_and_unlock with same context returns no new unlocks the second time."""
        user, _ = create_test_user(email="rerun@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        ctx = {"workout_count": 1, "prs_count": 1}
        first = check_and_unlock_achievements(seeded_db, user.id, ctx)
        seeded_db.commit()
        second = check_and_unlock_achievements(seeded_db, user.id, ctx)
        seeded_db.commit()

        assert len(first) > 0
        assert second == []

    def test_unknown_achievement_id_returns_none(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="bad@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        result = unlock_achievement(seeded_db, user.id, "does_not_exist")
        assert result is None


class TestListingHelpers:
    def test_get_user_achievements_shows_locked_and_unlocked(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="list@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlock_achievement(seeded_db, user.id, "first_workout")
        seeded_db.commit()

        achievements = get_user_achievements(seeded_db, user.id)

        first_workout = next(a for a in achievements if a["id"] == "first_workout")
        locked = next(a for a in achievements if a["id"] == "workout_100")

        assert first_workout["unlocked"] is True
        assert first_workout["unlocked_at"] is not None
        assert locked["unlocked"] is False
        assert locked["unlocked_at"] is None

    def test_get_recently_unlocked_orders_desc(self, seeded_db, create_test_user):
        user, _ = create_test_user(email="recent@example.com")
        get_or_create_user_progress(seeded_db, user.id)
        seeded_db.commit()

        unlock_achievement(seeded_db, user.id, "first_workout")
        seeded_db.commit()
        unlock_achievement(seeded_db, user.id, "pr_first")
        seeded_db.commit()

        recent = get_recently_unlocked(seeded_db, user.id, limit=5)

        assert len(recent) == 2
        # Most recent first
        assert recent[0]["id"] == "pr_first"
        assert recent[1]["id"] == "first_workout"


class TestSeedIdempotency:
    def test_seed_twice_does_not_duplicate(self, db):
        seed_achievement_definitions(db)
        first_count = db.query(AchievementDefinition).count()
        seed_achievement_definitions(db)
        second_count = db.query(AchievementDefinition).count()
        assert first_count == second_count
        assert first_count > 0
