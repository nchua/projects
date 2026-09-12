"""
ARISE v3 Phase 4 — the quest-table drop (spec §11).

Runs the ``v3_drop_quest_tables`` migration against a throwaway SQLite file
the same way ``test_v3_migrations`` does: upgrade on a schema that still
has the tables drops them, a second upgrade is a no-op, downgrade recreates
minimal tables (with the composite index the older migrations drop) and is
itself idempotent. The alembic graph keeps a single head.
"""
import importlib.util
import pathlib

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.core.database import Base

BACKEND = pathlib.Path(__file__).resolve().parent.parent
VERSIONS = BACKEND / "alembic" / "versions"
NAME = "v3_drop_quest_tables"
QUEST_TABLES = {"quest_definitions", "user_quests"}


def _load():
    spec = importlib.util.spec_from_file_location(f"mig_{NAME}", VERSIONS / f"{NAME}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, fn: str) -> None:
    module = _load()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn)()


def _tables(engine) -> set:
    return set(sa.inspect(engine).get_table_names())


def _indexes(engine, table: str) -> set:
    return {ix["name"] for ix in sa.inspect(engine).get_indexes(table)}


@pytest.fixture
def engine(tmp_path):
    eng = sa.create_engine(f"sqlite:///{tmp_path / 'quest_drop.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_single_head_chained_after_w0():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    # The control-plane migrations now chain after this one; the head moved.
    assert ScriptDirectory.from_config(cfg).get_heads() == ["purchase_verification"]
    module = _load()
    assert module.revision == NAME
    assert module.down_revision == "v3_campaign_tables"


def test_models_no_longer_register_quest_tables():
    assert not (QUEST_TABLES & set(Base.metadata.tables))
    with pytest.raises(ImportError):
        from app.models import QuestDefinition  # noqa: F401


def test_upgrade_drops_and_second_upgrade_is_noop(engine):
    # create_all no longer knows the quest tables; the downgrade recreates
    # the pre-v3 state so the drop has something to drop.
    assert not (QUEST_TABLES & _tables(engine))
    _run(engine, "downgrade")
    assert QUEST_TABLES <= _tables(engine)
    assert "ix_user_quests_user_date" in _indexes(engine, "user_quests")

    _run(engine, "upgrade")
    assert not (QUEST_TABLES & _tables(engine))
    before = _tables(engine)
    _run(engine, "upgrade")          # no-op on an already-dropped schema
    assert _tables(engine) == before


def test_downgrade_round_trip_is_idempotent(engine):
    _run(engine, "downgrade")
    with_tables = _tables(engine)
    _run(engine, "downgrade")        # no-op when the tables exist
    assert _tables(engine) == with_tables
    _run(engine, "upgrade")
    assert not (QUEST_TABLES & _tables(engine))
    _run(engine, "downgrade")
    assert QUEST_TABLES <= _tables(engine)
