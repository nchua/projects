"""
Exercise families (ARISE v3 §4.2): dict coverage, grouping rules, service.

The owner's logged names come from the prod usage snapshot; each must resolve
to the family the prescription engine anchors on. Front squat and incline
bench are deliberately NOT folded into the big-three families.
"""
import uuid
from datetime import datetime, timezone

import pytest

import seed_exercises
from app.models.exercise import Exercise
from app.models.exercise_family import ExerciseFamily
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession
from app.services.exercise_family_defs import (
    ALIAS_NAME_TO_FAMILY,
    BIG_THREE_FAMILIES,
    CANONICAL_NAME_TO_FAMILY,
    FAMILY_DEFS,
    family_for_name,
)
from app.services.exercise_family_service import (
    assign_family_ids,
    ensure_families,
    families_for_user,
    family_for_exercise,
)

NON_LOADABLE_CATEGORIES = {"Cardio", "Sport"}

OWNER_LOGGED_NAMES = {
    "Barbell Bench Press": "bench_press",
    "Barbell Back Squat": "back_squat",
    "Incline Barbell Bench Press": "incline_bench_press",
    "Seated Barbell Shoulder Press": "overhead_press",
    "Lat Pull Downs": "lat_pulldown",
    "Seated Machine Row": "machine_row",
    "Hamstring Curl": "leg_curl",
    "Leg Extensions": "leg_extension",
    "Dumbbell Shrugs": "db_shrug",
    "Shrugs": "barbell_shrug",
    "Lying Tricep Extension": "lying_tricep_extension",
    "Tricep Pushdowns": "tricep_pushdown",
    "Incline Dumbbell Curl": "incline_db_curl",
    "Dumbbell Curl": "db_curl",
    "One-Arm Preacher Curl": "preacher_curl",
    "Lateral Raises": "lateral_raise",
    "Dumbbell Flyes": "db_fly",
    "Crunches": "crunch",
    "Seated Calf Raises": "seated_calf_raise",
    "Machine Shoulder Press": "machine_shoulder_press",
}


class TestFamilyDefs:
    def test_every_loadable_seed_canonical_resolves(self):
        missing = [
            ex["name"]
            for ex in seed_exercises.exercises_data
            if ex["category"] not in NON_LOADABLE_CATEGORIES
            and ex["name"] not in CANONICAL_NAME_TO_FAMILY
        ]
        assert missing == []

    def test_cardio_and_sport_canonicals_have_no_family(self):
        leaked = [
            ex["name"]
            for ex in seed_exercises.exercises_data
            if ex["category"] in NON_LOADABLE_CATEGORIES
            and family_for_name(ex["name"]) is not None
        ]
        assert leaked == []

    def test_every_mapped_name_points_at_a_defined_family(self):
        for name, slug in {**CANONICAL_NAME_TO_FAMILY, **ALIAS_NAME_TO_FAMILY}.items():
            assert slug in FAMILY_DEFS, (name, slug)

    def test_seed_aliases_follow_their_canonical_except_documented_splits(self):
        splits = {"Dumbbell Shrugs": "db_shrug"}
        for ex in seed_exercises.exercises_data:
            fam = CANONICAL_NAME_TO_FAMILY.get(ex["name"])
            if fam is None:
                continue
            for alias in ex["aliases"]:
                expected = splits.get(alias, fam)
                assert family_for_name(alias) == expected, (ex["name"], alias)

    @pytest.mark.parametrize("name,slug", sorted(OWNER_LOGGED_NAMES.items()))
    def test_owner_logged_names_resolve(self, name, slug):
        assert family_for_name(name) == slug

    def test_name_matching_is_case_and_whitespace_insensitive(self):
        assert family_for_name("  lat pull  downs ") == "lat_pulldown"
        assert family_for_name("BARBELL BENCH PRESS") == "bench_press"
        assert family_for_name("Not A Real Movement") is None
        assert family_for_name("") is None

    def test_variants_are_not_folded_into_big_three(self):
        assert family_for_name("Incline Barbell Bench Press") != "bench_press"
        assert family_for_name("Dumbbell Bench Press") != "bench_press"
        assert family_for_name("Front Squat") != "back_squat"
        assert family_for_name("Goblet Squat") != "back_squat"
        assert family_for_name("Hack Squat") != "back_squat"
        assert family_for_name("Bulgarian Split Squat") != "back_squat"
        assert family_for_name("Sumo Deadlift") != "deadlift"
        assert family_for_name("Romanian Deadlift") != "deadlift"

    def test_big_three_flags(self):
        assert set(BIG_THREE_FAMILIES) == {"back_squat", "bench_press", "deadlift"}
        for slug in BIG_THREE_FAMILIES:
            assert FAMILY_DEFS[slug]["standards_key"] in {"squat", "bench", "deadlift"}

    def test_increments_are_plate_or_dumbbell_steps(self):
        for slug, defn in FAMILY_DEFS.items():
            assert defn["increment_lb"] in (2.5, 5.0), slug
        assert FAMILY_DEFS["db_curl"]["increment_lb"] == 2.5
        assert FAMILY_DEFS["back_squat"]["increment_lb"] == 5.0


def _seed_group(db, canonical_name: str, aliases=(), category="Push"):
    canonical_id = str(uuid.uuid4())
    rows = [Exercise(name=canonical_name, canonical_id=canonical_id, category=category, is_custom=False)]
    rows += [Exercise(name=a, canonical_id=canonical_id, category=category, is_custom=False) for a in aliases]
    db.add_all(rows)
    db.flush()
    return rows


def _log_session(db, user_id: str, exercises, *, deleted=False):
    session = WorkoutSession(
        user_id=user_id,
        date=datetime(2026, 9, 1, tzinfo=timezone.utc).replace(tzinfo=None),
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db.add(session)
    db.flush()
    for i, ex in enumerate(exercises):
        we = WorkoutExercise(session_id=session.id, exercise_id=ex.id, order_index=i)
        db.add(we)
        db.flush()
        db.add(Set(workout_exercise_id=we.id, weight=100, weight_lb=100, weight_unit=WeightUnit.LB, reps=5, set_number=1))
    db.flush()
    return session


class TestFamilyService:
    def test_ensure_families_is_idempotent(self, db):
        # conftest already seeded; a second call changes nothing.
        assert ensure_families(db) == 0
        assert db.query(ExerciseFamily).count() == len(FAMILY_DEFS)

    def test_assign_family_ids_inherits_through_canonical_and_is_idempotent(self, db):
        bench, alias = _seed_group(db, "Barbell Bench Press", ["Bench Press"])
        (front,) = _seed_group(db, "Front Squat", category="Legs")
        (run,) = _seed_group(db, "Running", category="Cardio")

        assert assign_family_ids(db, include_custom=False) >= 3
        db.refresh(bench)
        db.refresh(alias)
        db.refresh(front)
        db.refresh(run)
        assert bench.family_id == "bench_press"
        assert alias.family_id == "bench_press"
        assert front.family_id == "front_squat"
        assert run.family_id is None

        assert assign_family_ids(db, include_custom=False) == 0

    def test_assign_family_ids_name_matches_custom_rows(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("fam-custom"))
        custom = Exercise(name="lat pull downs", is_custom=True, user_id=user.id)
        unknown = Exercise(name="Mystery Machine", is_custom=True, user_id=user.id)
        db.add_all([custom, unknown])
        db.flush()

        assert assign_family_ids(db, include_custom=False) == 0
        db.refresh(custom)
        assert custom.family_id is None

        assert assign_family_ids(db, include_custom=True) == 1
        db.refresh(custom)
        db.refresh(unknown)
        assert custom.family_id == "lat_pulldown"
        assert unknown.family_id is None

    def test_alias_split_out_of_canonical_group(self, db):
        shrug, db_shrug = _seed_group(db, "Shrugs", ["Dumbbell Shrugs"], category="Accessories")
        assign_family_ids(db, include_custom=False)
        db.refresh(shrug)
        db.refresh(db_shrug)
        assert shrug.family_id == "barbell_shrug"
        assert db_shrug.family_id == "db_shrug"

    def test_families_for_user_groups_logged_exercises(self, db, create_test_user, unique_email):
        user, _ = create_test_user(email=unique_email("fam-user"))
        other, _ = create_test_user(email=unique_email("fam-other"))
        bench, alias = _seed_group(db, "Barbell Bench Press", ["Bench Press"])
        (front,) = _seed_group(db, "Front Squat", category="Legs")
        (deadlift,) = _seed_group(db, "Barbell Deadlift", category="Pull")
        assign_family_ids(db, include_custom=False)

        _log_session(db, user.id, [bench, front])
        _log_session(db, user.id, [alias])
        _log_session(db, user.id, [deadlift], deleted=True)   # soft-deleted: ignored
        _log_session(db, other.id, [deadlift])                # someone else's

        fams = {f["family_id"]: f for f in families_for_user(db, user.id)}
        assert set(fams) == {"bench_press", "front_squat"}
        assert fams["bench_press"]["exercise_ids"] == sorted([bench.id, alias.id])
        assert fams["bench_press"]["is_big_three"] is True
        assert fams["bench_press"]["increment_lb"] == 5.0
        assert fams["bench_press"]["display_name"] == "Bench Press"
        assert fams["front_squat"]["is_big_three"] is False
        assert families_for_user(db, "nobody") == []

    def test_family_for_exercise_falls_back_through_group_and_name(self, db):
        bench, alias = _seed_group(db, "Barbell Bench Press", ["BB Bench"])
        assign_family_ids(db, include_custom=False)
        assert family_for_exercise(db, bench.id) == "bench_press"

        # Unassigned alias in an assigned group resolves through its siblings.
        alias.family_id = None
        db.flush()
        assert family_for_exercise(db, alias.id) == "bench_press"

        # Unassigned, groupless row resolves by name; unknown ids are None.
        lone = Exercise(name="Leg Extensions", is_custom=True)
        db.add(lone)
        db.flush()
        assert family_for_exercise(db, lone.id) == "leg_extension"
        assert family_for_exercise(db, "missing") is None

    def test_custom_exercise_endpoint_name_matches_family(self, client, auth_headers, db, unique_email):
        headers, _ = auth_headers(email=unique_email("fam-api"))
        resp = client.post(
            "/exercises",
            json={"name": "Seated Machine Row", "category": "Pull"},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text
        row = db.query(Exercise).filter(Exercise.id == resp.json()["id"]).first()
        assert row.family_id == "machine_row"
