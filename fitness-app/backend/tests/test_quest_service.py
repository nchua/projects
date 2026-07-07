"""
Tests for the surviving quest_service helpers.

Daily-quest generation/claim (and the /quests API) were removed in ARISE v2
Phase 0. ``user_has_wearable`` and ``calculate_todays_workout_stats`` survive
because the Phase 1 Directive system will reuse them.
"""


class TestUserHasWearable:
    """user_has_wearable() — wearable HR source detection."""

    def test_no_wearable_for_fresh_user(self, db, create_test_user):
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="fresh@example.com")
        assert user_has_wearable(db, user.id) is False

    def test_wearable_via_whoop_connection(self, db, create_test_user):
        from app.models.whoop import WhoopConnection
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="whoop@example.com")
        db.add(WhoopConnection(user_id=user.id))
        db.flush()
        assert user_has_wearable(db, user.id) is True

    def test_wearable_via_recent_hr_session(self, db, create_test_user):
        from datetime import datetime, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="watch@example.com")
        db.add(WorkoutSession(
            user_id=user.id,
            date=datetime.now(timezone.utc).replace(tzinfo=None),
            hr_source="apple_watch",
        ))
        db.flush()
        assert user_has_wearable(db, user.id) is True

    def test_old_hr_session_does_not_count(self, db, create_test_user):
        from datetime import datetime, timedelta, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="stale@example.com")
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=40)
        db.add(WorkoutSession(user_id=user.id, date=old, hr_source="apple_watch"))
        db.flush()
        assert user_has_wearable(db, user.id) is False

    def test_session_without_hr_source_does_not_count(self, db, create_test_user):
        from datetime import datetime, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="nohr@example.com")
        db.add(WorkoutSession(
            user_id=user.id,
            date=datetime.now(timezone.utc).replace(tzinfo=None),
            hr_source=None,
        ))
        db.flush()
        assert user_has_wearable(db, user.id) is False


class TestCalculateTodaysWorkoutStats:
    """calculate_todays_workout_stats() — per-day aggregate stats."""

    def test_empty_day_returns_zeroes(self, db, create_test_user):
        from datetime import date

        from app.services.quest_service import calculate_todays_workout_stats
        user, _ = create_test_user(email="empty@example.com")

        stats = calculate_todays_workout_stats(db, user.id, date.today())

        assert stats["workout_count"] == 0
        assert stats["total_reps"] == 0
        assert stats["compound_sets"] == 0
        assert stats["total_volume"] == 0

    def test_only_target_date_counts(self, db, create_test_user):
        from datetime import datetime, timedelta, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import calculate_todays_workout_stats
        user, _ = create_test_user(email="dates@example.com")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(WorkoutSession(user_id=user.id, date=now))
        db.add(WorkoutSession(user_id=user.id, date=now - timedelta(days=2)))
        db.flush()

        stats = calculate_todays_workout_stats(db, user.id, now.date())

        assert stats["workout_count"] == 1

    def test_hr_fields_aggregate_across_day(self, db, create_test_user):
        from datetime import datetime, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import calculate_todays_workout_stats
        user, _ = create_test_user(email="hr@example.com")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(WorkoutSession(
            user_id=user.id, date=now,
            hr_zone_seconds={"z1": 600, "z2": 1200},
            peak_heart_rate=155, strain=10.5,
        ))
        db.add(WorkoutSession(
            user_id=user.id, date=now,
            hr_zone_seconds={"z3": 600},
            peak_heart_rate=170, strain=8.0,
        ))
        db.flush()

        stats = calculate_todays_workout_stats(db, user.id, now.date())

        # z2 (20 min) + z3 (10 min); z1 excluded from "elevated" zones.
        assert stats["elevated_zone_minutes"] == 30
        assert stats["peak_heart_rate"] == 170  # max of the day
        assert stats["strain"] == 10.5  # max of the day
