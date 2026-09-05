"""
ARISE v3 small foundations: daily_activity_series, the plateau rewrite
(>= 5 distinct local days in 28 days) and the quest_service helper move.
"""
from datetime import date, datetime, timedelta

import pytest

from app.models.activity import DailyActivity
from app.models.exercise import Exercise
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession
from app.services.activity_series import SERIES_KEYS, daily_activity_series


class TestDailyActivitySeries:
    def test_missing_days_present_with_nulls_oldest_first(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("series-empty"))
        series = daily_activity_series(db, user.id, 7)
        assert len(series) == 7
        assert [tuple(row) for row in series] == [SERIES_KEYS] * 7
        assert series[0]["local_date"] == (date.today() - timedelta(days=6)).isoformat()
        assert series[-1]["local_date"] == date.today().isoformat()
        assert all(row["sleep_hours"] is None and row["source"] is None for row in series)
        assert daily_activity_series(db, user.id, 0) == []

    def test_merges_sources_per_day_preferring_whoop(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("series-merge"))
        today = date.today()
        db.add_all([
            DailyActivity(
                user_id=user.id, date=today, source="apple_fitness",
                steps=8123, hrv=50, resting_heart_rate=55, sleep_hours=6.0,
            ),
            DailyActivity(
                user_id=user.id, date=today, source="whoop_api",
                sleep_hours=7.26, recovery_score=81, hrv=62, strain=12.345,
            ),
            DailyActivity(
                user_id=user.id, date=today - timedelta(days=1), source="apple_fitness",
                steps=4000, hrv=48,
            ),
            DailyActivity(  # outside the window
                user_id=user.id, date=today - timedelta(days=10), source="whoop_api",
                sleep_hours=9.0,
            ),
        ])
        db.flush()

        series = daily_activity_series(db, user.id, 3)
        assert [row["local_date"] for row in series] == [
            (today - timedelta(days=2)).isoformat(),
            (today - timedelta(days=1)).isoformat(),
            today.isoformat(),
        ]
        yesterday, merged = series[1], series[2]
        assert merged["sleep_hours"] == 7.3            # WHOOP wins, rounded to 1 dp
        assert merged["recovery_score"] == 81.0
        assert merged["strain"] == 12.3
        assert merged["hrv"] == 62.0                   # WHOOP first for HRV
        assert merged["resting_heart_rate"] == 55.0    # only Apple has RHR
        assert merged["steps"] == 8123.0
        assert merged["source"] == "whoop_api,apple_fitness"
        assert yesterday["hrv"] == 48.0 and yesterday["source"] == "apple_fitness"
        assert series[0]["source"] is None

    def test_whoop_missing_field_falls_back_to_other_source(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("series-fallback"))
        today = date.today()
        db.add_all([
            DailyActivity(user_id=user.id, date=today, source="whoop_api", recovery_score=70),
            DailyActivity(user_id=user.id, date=today, source="apple_fitness", hrv=44, sleep_hours=5.5),
        ])
        db.flush()
        (row,) = daily_activity_series(db, user.id, 1)
        assert row["hrv"] == 44.0
        assert row["sleep_hours"] == 5.5
        assert row["recovery_score"] == 70.0


def _log_e1rm_day(db, user_id: str, exercise: Exercise, day: date, e1rm: float, *, with_local_date=True):
    session = WorkoutSession(
        user_id=user_id,
        date=datetime(day.year, day.month, day.day),
        local_date=day if with_local_date else None,
    )
    db.add(session)
    db.flush()
    we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    db.add(Set(
        workout_exercise_id=we.id, weight=200, weight_lb=200, weight_unit=WeightUnit.LB,
        reps=5, set_number=1, e1rm=e1rm,
    ))
    db.flush()
    return session


class TestPlateauInsight:
    def _plateau_titles(self, db, user_id):
        from app.api.analytics import compute_insights
        return [i.title for i in compute_insights(db, user_id) if i.type.value == "plateau"]

    def test_five_distinct_local_days_flag_a_plateau(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("plateau-5"))
        ex = Exercise(name="Barbell Back Squat", is_custom=False, category="Legs")
        db.add(ex)
        db.flush()
        today = date.today()
        for k in range(5):
            _log_e1rm_day(db, user.id, ex, today - timedelta(days=2 * k), 250.0)
        assert self._plateau_titles(db, user.id) == ["Barbell Back Squat has plateaued"]

    def test_duplicate_days_do_not_count_twice(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("plateau-dup"))
        ex = Exercise(name="Barbell Back Squat", is_custom=False, category="Legs")
        db.add(ex)
        db.flush()
        today = date.today()
        for k in range(4):
            _log_e1rm_day(db, user.id, ex, today - timedelta(days=2 * k), 250.0)
        # A fifth session on an already-counted day: still only 4 distinct days.
        _log_e1rm_day(db, user.id, ex, today, 250.0)
        assert self._plateau_titles(db, user.id) == []

    def test_null_local_date_rows_fall_back_to_midnight_convention(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("plateau-null"))
        ex = Exercise(name="Barbell Back Squat", is_custom=False, category="Legs")
        db.add(ex)
        db.flush()
        today = date.today()
        for k in range(5):
            _log_e1rm_day(db, user.id, ex, today - timedelta(days=2 * k), 250.0, with_local_date=False)
        assert self._plateau_titles(db, user.id) == ["Barbell Back Squat has plateaued"]


class TestHelperMove:
    def test_directive_service_imports_from_workout_stats(self):
        import app.services.directive_service as directive_service
        from app.services.workout_stats import (
            calculate_todays_workout_stats,
            user_has_wearable,
        )
        assert directive_service.calculate_todays_workout_stats is calculate_todays_workout_stats
        assert callable(user_has_wearable)

    def test_quest_service_module_is_gone(self):
        with pytest.raises(ImportError):
            import app.services.quest_service  # noqa: F401
