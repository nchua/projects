"""
Tests for the HealthKit (Apple Watch) workout import — Chunk A.

Covers ``app.services.healthkit_service.import_healthkit_workouts`` and the
``POST /workouts/import-healthkit`` endpoint, mirroring the structure of
``tests/test_whoop_service.py``: real-DB seeding of ``Exercise`` /
``WorkoutSession`` / ``Set`` rows, asserting
dedup, cardio/strength routing, per-set HR attribution, response-contract
stability, and the round-trip endpoint (which also proves the
``_build_workout_response`` HR-population fix).

Contract under test (see ``docs/wearable-hr-v1-build-spec.md`` Contract Registry
+ Chunk A):
- Service signature:
  ``import_healthkit_workouts(db, user_id, workouts) -> dict`` with keys
  ``{"imported", "skipped_duplicates", "sessions_created", "sessions_updated",
  "unmatched", "quests_completed"}`` where ``unmatched`` is a list of dicts
  ``{"hk_uuid", "activity_type", "start", "end"}``.
- Request items are ``HealthKitWorkout`` (``app.schemas.healthkit``); HR samples
  reuse ``HeartRateSampleCreate`` (``app.schemas.workout``).
- ``hr_source`` is hard-stamped ``"apple_watch"`` server-side.
- ``WorkoutSession.hk_uuid`` is the dedup target.

These tests intentionally construct ``HealthKitWorkout`` instances (so the
schema validators run) and call the service directly, committing/flushing
ourselves the way the whoop tests do.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.exercise import Exercise
from app.models.workout import (
    Set,
    WeightUnit,
    WorkoutExercise,
    WorkoutSession,
)
from app.schemas.healthkit import HealthKitWorkout
from app.schemas.workout import HeartRateSampleCreate
from app.services.healthkit_service import import_healthkit_workouts

# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc(*args) -> datetime:
    """Aware UTC datetime."""
    return datetime(*args, tzinfo=timezone.utc)


def _iso_z(dt: datetime) -> str:
    """ISO8601 string with a trailing ``Z`` (mirrors the on-device formatter)."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_workout(
    *,
    hk_uuid: str = None,
    activity_type: str = "Running",
    is_strength: bool = False,
    start: datetime = None,
    duration_minutes: int = 45,
    avg_hr: int = None,
    peak_hr: int = None,
    kilojoules: float = None,
    hr_zone_seconds: dict = None,
    samples: list = None,
    distance_meters: float = None,
    mile_splits: list = None,
) -> HealthKitWorkout:
    """Build a validated ``HealthKitWorkout`` request item.

    Times are passed as ISO8601-``Z`` strings so the schema's ``parse_date``
    validator runs (mirrors how the client serializes them).
    """
    start = start or _utc(2026, 6, 1, 10, 0)
    end = start + timedelta(minutes=duration_minutes)
    return HealthKitWorkout(
        hk_uuid=hk_uuid or str(uuid.uuid4()),
        activity_type=activity_type,
        is_strength=is_strength,
        start=_iso_z(start),
        end=_iso_z(end),
        duration_seconds=duration_minutes * 60,
        kilojoules=kilojoules,
        avg_heart_rate=avg_hr,
        peak_heart_rate=peak_hr,
        hr_zone_seconds=hr_zone_seconds,
        heart_rate_samples=samples,
        distance_meters=distance_meters,
        mile_splits=mile_splits,
    )


def _seed_running_exercise(db) -> Exercise:
    """Seed a canonical 'Running' Sport/Cardio exercise the activity matcher hits.

    ``match_activity_to_exercise`` only searches non-custom exercises whose
    category is in ('Sport', 'Cardio', 'Flexibility', 'Strength'), so the
    category here is load-bearing.
    """
    ex = Exercise(
        id=str(uuid.uuid4()),
        name="Running",
        category="Cardio",
        is_custom=False,
    )
    db.add(ex)
    db.flush()
    return ex


def _seed_strength_session(db, user_id: str, when: datetime, *, with_set_times=False):
    """Seed a logged strength session (one exercise, one set) for overlap matching.

    ``when`` is stored naive-UTC the way the create path / DB store session dates.
    Returns (session, set). When ``with_set_times`` is True the set carries
    ``start_time``/``end_time`` so per-set HR attribution can slice samples.
    """
    naive = when.replace(tzinfo=None) if when.tzinfo else when
    exercise = Exercise(
        id=str(uuid.uuid4()),
        name="Barbell Back Squat",
        category="compound",
        is_custom=False,
    )
    db.add(exercise)
    session = WorkoutSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        date=naive,
        duration_minutes=60,
    )
    db.add(session)
    we = WorkoutExercise(
        id=str(uuid.uuid4()),
        session_id=session.id,
        exercise_id=exercise.id,
        order_index=0,
    )
    db.add(we)
    set_kwargs = dict(
        id=str(uuid.uuid4()),
        workout_exercise_id=we.id,
        weight=225,
        weight_unit=WeightUnit.LB,
        reps=5,
        set_number=1,
    )
    if with_set_times:
        set_kwargs["start_time"] = naive + timedelta(minutes=5)
        set_kwargs["end_time"] = naive + timedelta(minutes=7)
    s = Set(**set_kwargs)
    db.add(s)
    db.commit()
    return session, s


# ── TestDedup ─────────────────────────────────────────────────────────────────

class TestDedup:
    """Idempotency: a known hk_uuid (or an intra-batch duplicate) is skipped."""

    def test_skips_known_hk_uuid(self, db, create_test_user):
        """Re-importing the same hk_uuid skips it, creating no new rows."""
        user, _ = create_test_user(email=f"dedup1-{uuid.uuid4().hex[:8]}@example.com")
        _seed_running_exercise(db)
        hk_uuid = str(uuid.uuid4())

        first = import_healthkit_workouts(
            db, user.id, [_make_workout(hk_uuid=hk_uuid)]
        )
        db.commit()
        assert hk_uuid in first["imported"]
        assert len(first["sessions_created"]) == 1
        sessions_before = db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user.id
        ).count()

        # Second import of the same uuid -> skipped, nothing new.
        second = import_healthkit_workouts(
            db, user.id, [_make_workout(hk_uuid=hk_uuid)]
        )
        db.commit()
        assert hk_uuid in second["skipped_duplicates"]
        assert hk_uuid not in second["imported"]
        assert second["sessions_created"] == []
        assert second["sessions_updated"] == []
        sessions_after = db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user.id
        ).count()
        assert sessions_after == sessions_before

    def test_dedup_within_single_batch(self, db, create_test_user):
        """Two items with the same hk_uuid in one batch -> one imported, one skipped."""
        user, _ = create_test_user(email=f"dedup2-{uuid.uuid4().hex[:8]}@example.com")
        _seed_running_exercise(db)
        hk_uuid = str(uuid.uuid4())

        result = import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(hk_uuid=hk_uuid),
                _make_workout(hk_uuid=hk_uuid, start=_utc(2026, 6, 1, 12, 0)),
            ],
        )
        db.commit()

        assert result["imported"].count(hk_uuid) == 1
        assert hk_uuid in result["skipped_duplicates"]
        # Exactly one session created from the de-duplicated batch.
        assert len(result["sessions_created"]) == 1
        assert db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user.id,
            WorkoutSession.hk_uuid == hk_uuid,
        ).count() == 1


# ── TestCardioBackfill ────────────────────────────────────────────────────────

def _seed_legacy_cardio_session(db, user_id: str, hk_uuid: str) -> WorkoutSession:
    """Seed a cardio session as the pre-``add_cardio_distance`` import wrote it:
    hk_uuid consumed, but activity_type/distance_meters/duration_seconds NULL."""
    session = WorkoutSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        date=_utc(2026, 6, 1, 10, 0).replace(tzinfo=None),
        duration_minutes=45,
        hk_uuid=hk_uuid,
        hr_source="apple_watch",
        notes="running - Apple Watch",
    )
    db.add(session)
    db.commit()
    return session


class TestCardioBackfill:
    """A duplicate cardio workout NULL-fills missing distance fields (re-sync)."""

    def test_duplicate_cardio_backfills_null_fields(self, db, create_test_user):
        """Legacy row (NULL cardio fields) + re-sent duplicate -> fields filled."""
        user, _ = create_test_user(email=f"backfill1-{uuid.uuid4().hex[:8]}@example.com")
        hk_uuid = str(uuid.uuid4())
        session = _seed_legacy_cardio_session(db, user.id, hk_uuid)

        result = import_healthkit_workouts(
            db, user.id,
            [_make_workout(hk_uuid=hk_uuid, activity_type="running",
                           distance_meters=5012.0, mile_splits=[578, 585, 561])],
        )
        db.commit()

        assert result["sessions_updated"] == [session.id]
        # Acknowledged like the strength-update path, so clients mark it sent.
        assert hk_uuid in result["imported"]
        assert hk_uuid not in result["skipped_duplicates"]
        assert result["sessions_created"] == []
        db.refresh(session)
        assert session.activity_type == "running"
        assert session.distance_meters == 5012.0
        assert session.duration_seconds == 45 * 60
        assert session.mile_splits == [578, 585, 561]
        # No new session materialized.
        assert db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user.id
        ).count() == 1

    def test_backfill_never_clobbers_existing_values(self, db, create_test_user):
        """Non-NULL fields are left alone; a full row means plain skip."""
        user, _ = create_test_user(email=f"backfill2-{uuid.uuid4().hex[:8]}@example.com")
        hk_uuid = str(uuid.uuid4())
        session = _seed_legacy_cardio_session(db, user.id, hk_uuid)
        session.activity_type = "cycling"
        session.distance_meters = 9000.0
        session.duration_seconds = 2000
        session.mile_splits = [700, 710]
        db.commit()

        result = import_healthkit_workouts(
            db, user.id,
            [_make_workout(hk_uuid=hk_uuid, activity_type="running",
                           distance_meters=5012.0, mile_splits=[578, 585])],
        )
        db.commit()

        assert hk_uuid in result["skipped_duplicates"]
        assert result["sessions_updated"] == []
        db.refresh(session)
        assert session.activity_type == "cycling"
        assert session.distance_meters == 9000.0
        assert session.duration_seconds == 2000
        assert session.mile_splits == [700, 710]

    def test_backfill_idempotent_on_resend(self, db, create_test_user):
        """Second identical re-sync pass is a plain skip (nothing left to fill)."""
        user, _ = create_test_user(email=f"backfill3-{uuid.uuid4().hex[:8]}@example.com")
        hk_uuid = str(uuid.uuid4())
        _seed_legacy_cardio_session(db, user.id, hk_uuid)
        workout = _make_workout(hk_uuid=hk_uuid, activity_type="running",
                                distance_meters=5012.0)

        first = import_healthkit_workouts(db, user.id, [workout])
        db.commit()
        assert len(first["sessions_updated"]) == 1

        second = import_healthkit_workouts(db, user.id, [workout])
        db.commit()
        assert second["sessions_updated"] == []
        assert hk_uuid in second["skipped_duplicates"]

    def test_cardio_create_stores_mile_splits(self, db, create_test_user):
        """A fresh cardio import persists mile_splits alongside distance."""
        user, _ = create_test_user(email=f"splits1-{uuid.uuid4().hex[:8]}@example.com")
        _seed_running_exercise(db)
        hk_uuid = str(uuid.uuid4())

        result = import_healthkit_workouts(
            db, user.id,
            [_make_workout(hk_uuid=hk_uuid, activity_type="running",
                           distance_meters=5012.0, mile_splits=[578, 585, 561])],
        )
        db.commit()

        session = db.query(WorkoutSession).filter(
            WorkoutSession.id == result["sessions_created"][0]
        ).one()
        assert session.mile_splits == [578, 585, 561]
        assert session.distance_meters == 5012.0

    def test_mile_splits_rejects_nonpositive(self):
        """Schema validation: zero/negative splits are rejected."""
        import pytest

        with pytest.raises(ValueError):
            _make_workout(mile_splits=[578, 0, 561])

    def test_duplicate_strength_is_not_backfilled(self, db, create_test_user):
        """The backfill is cardio-only: a duplicate strength workout still skips."""
        user, _ = create_test_user(email=f"backfill4-{uuid.uuid4().hex[:8]}@example.com")
        hk_uuid = str(uuid.uuid4())
        session = _seed_legacy_cardio_session(db, user.id, hk_uuid)

        result = import_healthkit_workouts(
            db, user.id,
            [_make_workout(hk_uuid=hk_uuid, activity_type="strength_training",
                           is_strength=True, distance_meters=100.0)],
        )
        db.commit()

        assert hk_uuid in result["skipped_duplicates"]
        assert result["sessions_updated"] == []
        db.refresh(session)
        assert session.activity_type is None
        assert session.distance_meters is None


# ── TestCardioImport ──────────────────────────────────────────────────────────

class TestCardioImport:
    """Cardio (is_strength=false) creates a synthetic session, stamps source."""

    def test_run_creates_session_with_matched_exercise(self, db, create_test_user):
        """A run creates a session: apple_watch source, zones verbatim, exercise linked."""
        user, _ = create_test_user(email=f"cardio1-{uuid.uuid4().hex[:8]}@example.com")
        running = _seed_running_exercise(db)
        hk_uuid = str(uuid.uuid4())
        zones = {"z2": 540, "z3": 300}

        result = import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(
                    hk_uuid=hk_uuid,
                    activity_type="running",  # canonical HKWorkoutActivityType string (Chunk C map); fuzz-matches "Running"
                    is_strength=False,
                    avg_hr=145,
                    peak_hr=178,
                    kilojoules=1500.0,
                    hr_zone_seconds=zones,
                )
            ],
        )
        db.commit()

        assert hk_uuid in result["imported"]
        assert len(result["sessions_created"]) == 1
        session_id = result["sessions_created"][0]

        session = db.query(WorkoutSession).filter(
            WorkoutSession.id == session_id
        ).first()
        assert session is not None
        assert session.hk_uuid == hk_uuid
        assert session.hr_source == "apple_watch"   # hard-stamped server-side
        assert session.avg_heart_rate == 145
        assert session.peak_heart_rate == 178
        assert session.hr_zone_seconds == zones      # stored verbatim
        # Apple Watch never supplies strain.
        assert session.strain is None

        # The run is linked to the canonical Running exercise (one exercise, no sets).
        db.refresh(session)
        exercise_ids = [we.exercise_id for we in session.workout_exercises]
        assert running.id in exercise_ids
        assert all(len(we.sets) == 0 for we in session.workout_exercises)

    def test_unknown_activity_creates_exerciseless_session(self, db, create_test_user):
        """An activity with no matching exercise still creates a session (no exercise)."""
        user, _ = create_test_user(email=f"cardio2-{uuid.uuid4().hex[:8]}@example.com")
        # Deliberately seed only Running; "Underwater Hockey" won't match.
        _seed_running_exercise(db)
        hk_uuid = str(uuid.uuid4())

        result = import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(
                    hk_uuid=hk_uuid,
                    activity_type="Underwater Hockey",
                    is_strength=False,
                    avg_hr=120,
                )
            ],
        )
        db.commit()

        assert hk_uuid in result["imported"]
        assert len(result["sessions_created"]) == 1
        session = db.query(WorkoutSession).filter(
            WorkoutSession.id == result["sessions_created"][0]
        ).first()
        assert session is not None
        assert session.hr_source == "apple_watch"
        db.refresh(session)
        # No exercise linked because nothing matched.
        assert session.workout_exercises == []


# ── TestStrengthImport ────────────────────────────────────────────────────────

class TestStrengthImport:
    """Strength routes to an overlapping logged session; HR backfilled non-destructively."""

    def test_matches_overlapping_session_and_backfills_hr(self, db, create_test_user):
        """An overlapping strength workout sets hk_uuid + backfills HR into the session."""
        user, _ = create_test_user(email=f"str1-{uuid.uuid4().hex[:8]}@example.com")
        # Logged session 10:00-11:00; HK workout 10:05-10:50 overlaps.
        session, _set = _seed_strength_session(db, user.id, _utc(2026, 6, 1, 10, 0))
        hk_uuid = str(uuid.uuid4())

        result = import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(
                    hk_uuid=hk_uuid,
                    activity_type="Functional Strength Training",
                    is_strength=True,
                    start=_utc(2026, 6, 1, 10, 5),
                    duration_minutes=45,
                    avg_hr=132,
                    peak_hr=160,
                    hr_zone_seconds={"z2": 600},
                )
            ],
        )
        db.commit()

        assert session.id in result["sessions_updated"]
        assert result["sessions_created"] == []
        assert hk_uuid in result["imported"]
        # No new session created for the strength match.
        assert db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user.id
        ).count() == 1

        db.refresh(session)
        assert session.hk_uuid == hk_uuid
        assert session.avg_heart_rate == 132
        assert session.peak_heart_rate == 160
        assert session.hr_zone_seconds == {"z2": 600}
        assert session.hr_source == "apple_watch"

    def test_per_set_hr_attribution(self, db, create_test_user):
        """HR samples inside a set's [start_time, end_time] populate that set's avg/peak."""
        user, _ = create_test_user(email=f"str2-{uuid.uuid4().hex[:8]}@example.com")
        base = _utc(2026, 6, 1, 10, 0)
        # Set window is 10:05-10:07 (see _seed_strength_session with_set_times).
        session, the_set = _seed_strength_session(
            db, user.id, base, with_set_times=True
        )
        hk_uuid = str(uuid.uuid4())

        # Three samples inside the set window, one well outside it.
        samples = [
            HeartRateSampleCreate(timestamp=_iso_z(base + timedelta(minutes=5, seconds=10)), bpm=150),
            HeartRateSampleCreate(timestamp=_iso_z(base + timedelta(minutes=6)), bpm=160),
            HeartRateSampleCreate(timestamp=_iso_z(base + timedelta(minutes=6, seconds=50)), bpm=170),
            HeartRateSampleCreate(timestamp=_iso_z(base + timedelta(minutes=30)), bpm=110),  # outside
        ]

        import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(
                    hk_uuid=hk_uuid,
                    activity_type="Traditional Strength Training",
                    is_strength=True,
                    start=base + timedelta(minutes=5),
                    duration_minutes=30,
                    samples=samples,
                )
            ],
        )
        db.commit()

        db.refresh(the_set)
        # avg of the 3 in-window samples (150,160,170) -> 160; peak 170.
        assert the_set.avg_heart_rate == 160
        assert the_set.peak_heart_rate == 170

        # The raw samples were persisted; in-window ones carry this set's id.
        from app.models.workout import HeartRateSample
        attributed = db.query(HeartRateSample).filter(
            HeartRateSample.session_id == session.id,
            HeartRateSample.set_id == the_set.id,
        ).all()
        assert len(attributed) == 3
        assert all(s.source == "apple_watch" for s in attributed)

    def test_non_destructive_does_not_clobber(self, db, create_test_user):
        """Existing HR on the matched session is preserved; only empty fields fill."""
        user, _ = create_test_user(email=f"str3-{uuid.uuid4().hex[:8]}@example.com")
        session, _set = _seed_strength_session(db, user.id, _utc(2026, 6, 1, 10, 0))
        # Pre-existing HR on the session (e.g. logged live).
        session.avg_heart_rate = 999
        session.hr_source = "apple_watch"
        db.commit()

        import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(
                    hk_uuid=str(uuid.uuid4()),
                    activity_type="Functional Strength Training",
                    is_strength=True,
                    start=_utc(2026, 6, 1, 10, 5),
                    duration_minutes=30,
                    avg_hr=132,    # must NOT overwrite the existing 999
                    peak_hr=160,   # empty -> may fill
                )
            ],
        )
        db.commit()

        db.refresh(session)
        assert session.avg_heart_rate == 999          # not clobbered
        assert session.peak_heart_rate == 160         # was empty -> filled
        assert session.hr_source == "apple_watch"

    def test_no_match_goes_to_unmatched_and_hk_uuid_not_consumed(self, db, create_test_user):
        """A strength workout with no overlapping session is reported, not created.

        The hk_uuid is deliberately NOT consumed so a later import (once the lift
        is logged) can attach.
        """
        user, _ = create_test_user(email=f"str4-{uuid.uuid4().hex[:8]}@example.com")
        # No logged session at all -> no overlap possible.
        hk_uuid = str(uuid.uuid4())
        start = _utc(2026, 6, 1, 10, 0)

        result = import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(
                    hk_uuid=hk_uuid,
                    activity_type="Functional Strength Training",
                    is_strength=True,
                    start=start,
                    duration_minutes=45,
                )
            ],
        )
        db.commit()

        # Reported as an unmatched object (dict), nothing created/updated.
        assert result["sessions_created"] == []
        assert result["sessions_updated"] == []
        assert hk_uuid not in result["imported"]
        assert len(result["unmatched"]) == 1
        um = result["unmatched"][0]
        assert um["hk_uuid"] == hk_uuid
        assert um["activity_type"] == "Functional Strength Training"
        assert "start" in um and "end" in um

        # No session was created, and the uuid is NOT consumed (no row carries it),
        # so a later import can still attach once the session exists.
        assert db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user.id,
        ).count() == 0
        assert db.query(WorkoutSession).filter(
            WorkoutSession.hk_uuid == hk_uuid,
        ).count() == 0

    def test_two_strength_workouts_one_session_match_once(self, db, create_test_user):
        """Two strength workouts overlapping ONE logged session in a batch.

        Regression for the dedup-key-clobber bug: only one workout may attach;
        the other must be reported as unmatched (a session is claimed by exactly
        one HK workout). The matched session must appear once in
        ``sessions_updated``, carry exactly the attached uuid, and have its HR
        samples ingested once (no double-ingest), and a re-import of the same
        batch must fully dedup the attached uuid.
        """
        from app.models.workout import HeartRateSample

        user, _ = create_test_user(email=f"str5-{uuid.uuid4().hex[:8]}@example.com")
        base = _utc(2026, 6, 1, 10, 0)
        session, _set = _seed_strength_session(
            db, user.id, base, with_set_times=True
        )

        u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
        # Identical samples on both, so whichever attaches ingests the same 2.
        samples = [
            {"timestamp": _iso_z(base + timedelta(minutes=5, seconds=30)), "bpm": 150},
            {"timestamp": _iso_z(base + timedelta(minutes=6, seconds=30)), "bpm": 170},
        ]
        workouts = [
            _make_workout(
                hk_uuid=u1, activity_type="Functional Strength Training",
                is_strength=True, start=base + timedelta(minutes=5),
                duration_minutes=30, samples=samples,
            ),
            _make_workout(
                hk_uuid=u2, activity_type="Functional Strength Training",
                is_strength=True, start=base + timedelta(minutes=6),
                duration_minutes=30, samples=samples,
            ),
        ]

        result = import_healthkit_workouts(db, user.id, workouts)
        db.commit()

        # Exactly one attaches; the other is unmatched (NOT double-matched).
        assert result["sessions_updated"] == [session.id]
        assert len(result["imported"]) == 1
        assert len(result["unmatched"]) == 1
        attached = result["imported"][0]
        unmatched_uuid = result["unmatched"][0]["hk_uuid"]
        assert {attached, unmatched_uuid} == {u1, u2}

        db.refresh(session)
        assert session.hk_uuid == attached

        # Samples ingested once (2), not doubled (4) by a second spurious match.
        assert db.query(HeartRateSample).filter(
            HeartRateSample.session_id == session.id
        ).count() == 2

        # Re-import: the attached uuid is fully deduped (no re-ingest); the
        # unmatched one stays unmatched (no session free to attach to).
        result2 = import_healthkit_workouts(db, user.id, workouts)
        db.commit()
        assert attached in result2["skipped_duplicates"]
        assert result2["sessions_created"] == []
        assert result2["sessions_updated"] == []
        assert len(result2["unmatched"]) == 1
        assert result2["unmatched"][0]["hk_uuid"] == unmatched_uuid
        assert db.query(HeartRateSample).filter(
            HeartRateSample.session_id == session.id
        ).count() == 2


# ── TestQuestsCompletedContract ──────────────────────────────────────────────

class TestQuestsCompletedContract:
    """Daily quests were removed in Phase 0; the response key stays (empty)."""

    def test_quests_completed_always_empty(self, db, create_test_user):
        """A cardio import still returns the quests_completed key, always []."""
        user, _ = create_test_user(email=f"quest-{uuid.uuid4().hex[:8]}@example.com")
        _seed_running_exercise(db)

        today = datetime.now(timezone.utc).date()
        start = datetime(today.year, today.month, today.day, 10, 0, tzinfo=timezone.utc)

        result = import_healthkit_workouts(
            db,
            user.id,
            [
                _make_workout(
                    hk_uuid=str(uuid.uuid4()),
                    activity_type="Outdoor Run",
                    is_strength=False,
                    start=start,
                    duration_minutes=45,
                    avg_hr=150,
                    peak_hr=175,
                    hr_zone_seconds={"z2": 600, "z3": 360},
                )
            ],
        )
        db.commit()

        assert result["quests_completed"] == []


# ── TestEndpoint (round-trip through the API) ─────────────────────────────────

class TestEndpoint:
    """The POST endpoint requires auth and round-trips HR through GET."""

    def test_requires_auth(self, client):
        """No bearer token -> 401/403."""
        resp = client.post(
            "/workouts/import-healthkit",
            json={"workouts": []},
        )
        assert resp.status_code in (401, 403)

    def test_round_trip(self, db, client, auth_headers):
        """POST returns 200 with all 6 response keys; GET returns session + set HR.

        This proves the ``_build_workout_response`` fix: the session and set HR
        fields actually serialize on the GET.
        """
        headers, user = auth_headers(email=f"ep-{uuid.uuid4().hex[:8]}@example.com")
        _seed_running_exercise(db)

        hk_uuid = str(uuid.uuid4())
        start = _utc(2026, 6, 1, 10, 0)
        payload = {
            "workouts": [
                {
                    "hk_uuid": hk_uuid,
                    "activity_type": "Outdoor Run",
                    "is_strength": False,
                    "start": _iso_z(start),
                    "end": _iso_z(start + timedelta(minutes=45)),
                    "duration_seconds": 45 * 60,
                    "avg_heart_rate": 148,
                    "peak_heart_rate": 176,
                    "kilojoules": 1480.0,
                    "hr_zone_seconds": {"z2": 540, "z3": 300},
                    "distance_meters": 7500.0,
                    "mile_splits": [578, 585, 561, 590],
                }
            ]
        }

        resp = client.post(
            "/workouts/import-healthkit", json=payload, headers=headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # All six response keys present.
        for key in (
            "imported",
            "skipped_duplicates",
            "sessions_created",
            "sessions_updated",
            "unmatched",
            "quests_completed",
        ):
            assert key in body, f"missing response key: {key}"

        assert hk_uuid in body["imported"]
        assert len(body["sessions_created"]) == 1
        session_id = body["sessions_created"][0]

        # GET the session back -> session-level HR fields are populated
        # (proves the _build_workout_response fix).
        get_resp = client.get(f"/workouts/{session_id}", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        workout = get_resp.json()
        assert workout["avg_heart_rate"] == 148
        assert workout["peak_heart_rate"] == 176
        assert workout["hr_source"] == "apple_watch"
        assert workout["hr_zone_seconds"] == {"z2": 540, "z3": 300}
        # Cardio metadata serializes on the GET (distance/pace/splits UI).
        assert workout["distance_meters"] == 7500.0
        assert workout["duration_seconds"] == 45 * 60
        assert workout["mile_splits"] == [578, 585, 561, 590]
        # SetResponse HR fields exist in the schema; for cardio there are no sets,
        # so just assert the schema shape is intact.
        assert "exercises" in workout

    def test_round_trip_strength_per_set_hr(self, db, client, auth_headers):
        """A strength import surfaces per-set HR fields on GET (set HR serialization)."""
        headers, user = auth_headers(email=f"ep2-{uuid.uuid4().hex[:8]}@example.com")
        base = _utc(2026, 6, 1, 10, 0)
        session, the_set = _seed_strength_session(
            db, user.id, base, with_set_times=True
        )

        payload = {
            "workouts": [
                {
                    "hk_uuid": str(uuid.uuid4()),
                    "activity_type": "Functional Strength Training",
                    "is_strength": True,
                    "start": _iso_z(base + timedelta(minutes=5)),
                    "end": _iso_z(base + timedelta(minutes=35)),
                    "duration_seconds": 30 * 60,
                    "heart_rate_samples": [
                        {"timestamp": _iso_z(base + timedelta(minutes=5, seconds=30)), "bpm": 150},
                        {"timestamp": _iso_z(base + timedelta(minutes=6, seconds=30)), "bpm": 170},
                    ],
                }
            ]
        }

        resp = client.post(
            "/workouts/import-healthkit", json=payload, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert session.id in resp.json()["sessions_updated"]

        get_resp = client.get(f"/workouts/{session.id}", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        workout = get_resp.json()
        # Find the seeded set and confirm its HR fields round-tripped.
        all_sets = [s for ex in workout["exercises"] for s in ex["sets"]]
        assert all_sets, "expected at least one set on the strength session"
        target = next((s for s in all_sets if s["id"] == the_set.id), all_sets[0])
        assert target["avg_heart_rate"] is not None
        assert target["peak_heart_rate"] is not None
        # The two in-window samples (150, 170) -> avg 160, peak 170.
        assert target["avg_heart_rate"] == 160
        assert target["peak_heart_rate"] == 170
