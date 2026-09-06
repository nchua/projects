"""
ARISE v3 foundation migrations — idempotency and round-trip on SQLite.

The three v3 migrations chain from ``workout_local_date`` and must survive
prod stamp drift (a re-run on an already-migrated schema is a no-op) and
CI's ``upgrade heads`` → downgrade → ``upgrade heads`` on Postgres. Here they
run against a throwaway SQLite file built by ``Base.metadata.create_all``
(the "already applied" state), are downgraded to the pre-v3 state, then
upgraded twice and round-tripped again. Each migration's ``op`` proxy is
bound with ``Operations.context`` — no alembic env / version table involved.
"""
import importlib.util
import pathlib
import uuid

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.core.database import Base
from app.services.exercise_family_defs import FAMILY_DEFS

BACKEND = pathlib.Path(__file__).resolve().parent.parent
VERSIONS = BACKEND / "alembic" / "versions"
CHAIN = ["v3_sets_columns", "v3_exercise_families", "v3_campaign_tables"]

NEW_TABLES = {
    "exercise_families",
    "campaigns",
    "campaign_arcs",
    "hunt_templates",
    "planned_hunts",
    "daily_training_load",
    "coach_outputs",
}
NEW_COLUMNS = {
    "sets": {"weight_lb", "is_bodyweight", "is_warmup"},
    "workout_sessions": {"training_load", "load_estimated"},
    "exercises": {"family_id"},
    "goals": {"campaign_id", "kind", "target_miles", "run_scope", "deadline_extensions"},
    "pr_gates": {"family_id", "planned_hunt_id"},
    "user_profiles": {"injury_notes", "run_hr_cap_bpm"},
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"v3mig_{name}", VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, name: str, fn: str) -> None:
    module = _load(name)
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn)()


def _upgrade_all(engine):
    for name in CHAIN:
        _run(engine, name, "upgrade")


def _downgrade_all(engine):
    for name in reversed(CHAIN):
        _run(engine, name, "downgrade")


def _tables(engine) -> set:
    return set(sa.inspect(engine).get_table_names())


def _columns(engine, table: str) -> set:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def _schema_snapshot(engine) -> dict:
    insp = sa.inspect(engine)
    return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}


def _assert_v3_present(engine):
    assert NEW_TABLES <= _tables(engine)
    for table, cols in NEW_COLUMNS.items():
        assert cols <= _columns(engine, table), (table, cols - _columns(engine, table))


def _assert_v3_absent(engine):
    assert not (NEW_TABLES & _tables(engine))
    for table, cols in NEW_COLUMNS.items():
        assert not (cols & _columns(engine, table)), (table, cols & _columns(engine, table))


@pytest.fixture
def engine(tmp_path):
    """Fresh file-backed SQLite with the full current schema (create_all)."""
    eng = sa.create_engine(f"sqlite:///{tmp_path / 'v3_migrations.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_alembic_has_exactly_one_head():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    # The control-plane migrations chain after the v3 quest-table drop.
    assert heads == ["admin_seed_backfill"]


def test_chain_is_linear_from_workout_local_date():
    assert _load("v3_sets_columns").down_revision == "workout_local_date"
    assert _load("v3_exercise_families").down_revision == "v3_sets_columns"
    assert _load("v3_campaign_tables").down_revision == "v3_exercise_families"


def test_upgrade_on_already_migrated_schema_is_noop(engine):
    """Prod stamp-drift scenario: the columns exist, the version table lies."""
    before = _schema_snapshot(engine)
    _upgrade_all(engine)
    assert _schema_snapshot(engine) == before
    # Families were seeded into the (empty) create_all table, and only once.
    with engine.connect() as conn:
        n = conn.execute(sa.text("SELECT count(*) FROM exercise_families")).scalar()
    assert n == len(FAMILY_DEFS)
    _upgrade_all(engine)
    with engine.connect() as conn:
        n2 = conn.execute(sa.text("SELECT count(*) FROM exercise_families")).scalar()
    assert n2 == n


def test_downgrade_then_upgrade_round_trips(engine):
    _downgrade_all(engine)
    _assert_v3_absent(engine)

    _upgrade_all(engine)
    _assert_v3_present(engine)
    after_first = _schema_snapshot(engine)

    # Second upgrade run must be a no-op with the schema intact.
    _upgrade_all(engine)
    assert _schema_snapshot(engine) == after_first

    _downgrade_all(engine)
    _assert_v3_absent(engine)
    # Downgrade is itself idempotent.
    _downgrade_all(engine)
    _assert_v3_absent(engine)

    _upgrade_all(engine)
    _assert_v3_present(engine)


def test_sets_backfill_normalizes_kg_to_lb(engine):
    _downgrade_all(engine)
    kg_id, lb_id = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        # FK enforcement is off on this engine, so bare rows are fine.
        conn.execute(sa.text(
            "INSERT INTO sets (id, workout_exercise_id, weight, weight_unit, reps, set_number, created_at) "
            "VALUES (:id, 'we', 100, 'KG', 5, 1, '2026-09-05 00:00:00')"
        ), {"id": kg_id})
        conn.execute(sa.text(
            "INSERT INTO sets (id, workout_exercise_id, weight, weight_unit, reps, set_number, created_at) "
            "VALUES (:id, 'we', 135, 'LB', 5, 2, '2026-09-05 00:00:00')"
        ), {"id": lb_id})

    _run(engine, "v3_sets_columns", "upgrade")
    with engine.connect() as conn:
        rows = dict(conn.execute(sa.text("SELECT id, weight_lb FROM sets")).fetchall())
        flags = conn.execute(sa.text("SELECT is_bodyweight, is_warmup FROM sets")).fetchall()
    assert rows[kg_id] == pytest.approx(220.462, abs=0.01)
    assert rows[lb_id] == 135
    assert all(not bw and not wu for bw, wu in flags)

    # Re-run: backfill only touches NULLs, so values are unchanged.
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE sets SET weight_lb = 1 WHERE id = :id"), {"id": lb_id})
    _run(engine, "v3_sets_columns", "upgrade")
    with engine.connect() as conn:
        assert conn.execute(
            sa.text("SELECT weight_lb FROM sets WHERE id = :id"), {"id": lb_id}
        ).scalar() == 1


def test_exercise_families_migration_seeds_and_assigns(engine):
    _downgrade_all(engine)
    canonical_id = str(uuid.uuid4())
    ids = {name: str(uuid.uuid4()) for name in ("Barbell Bench Press", "Bench Press", "Front Squat", "Running", "My Custom Bench")}
    now = "2026-09-05 00:00:00"
    with engine.begin() as conn:
        for name, cid, custom in [
            ("Barbell Bench Press", canonical_id, False),
            ("Bench Press", canonical_id, False),
            ("Front Squat", str(uuid.uuid4()), False),
            ("Running", str(uuid.uuid4()), False),
            ("My Custom Bench", None, True),
        ]:
            conn.execute(sa.text(
                "INSERT INTO exercises (id, name, canonical_id, category, is_custom, created_at, updated_at) "
                "VALUES (:id, :name, :cid, 'Push', :custom, :now, :now)"
            ), {"id": ids[name], "name": name, "cid": cid, "custom": custom, "now": now})

    _run(engine, "v3_sets_columns", "upgrade")
    _run(engine, "v3_exercise_families", "upgrade")

    def _families():
        with engine.connect() as conn:
            return dict(conn.execute(sa.text("SELECT id, family_id FROM exercises")).fetchall())

    fams = _families()
    assert fams[ids["Barbell Bench Press"]] == "bench_press"
    assert fams[ids["Bench Press"]] == "bench_press"          # alias inherits
    assert fams[ids["Front Squat"]] == "front_squat"          # not back_squat
    assert fams[ids["Running"]] is None                       # cardio stays NULL
    assert fams[ids["My Custom Bench"]] is None               # custom rows are the script's job
    with engine.connect() as conn:
        n = conn.execute(sa.text("SELECT count(*) FROM exercise_families")).scalar()
        big3 = conn.execute(
            sa.text("SELECT id FROM exercise_families WHERE is_big_three")
        ).fetchall()
    assert n == len(FAMILY_DEFS)
    assert {r[0] for r in big3} == {"back_squat", "bench_press", "deadlift"}

    # Re-run is a no-op.
    _run(engine, "v3_exercise_families", "upgrade")
    assert _families() == fams
