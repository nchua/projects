"""Shared scaffolding for running alembic revisions directly against a throwaway engine."""
from __future__ import annotations

import importlib.util
import pathlib
from types import ModuleType
from typing import Iterable

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

BACKEND = pathlib.Path(__file__).resolve().parent.parent
VERSIONS = BACKEND / "alembic" / "versions"


def load_module(path: pathlib.Path, name: str) -> ModuleType:
    """Import a standalone Python file (migration, script) under ``name``."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_migration(name: str) -> ModuleType:
    return load_module(VERSIONS / f"{name}.py", f"migration_{name}")


def run_migration(engine, name: str, fn: str) -> None:
    """Run ``upgrade``/``downgrade`` of one revision with ``op`` bound to ``engine``."""
    module = load_migration(name)
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn)()


def upgrade_all(engine, chain: Iterable[str]) -> None:
    for name in chain:
        run_migration(engine, name, "upgrade")


def downgrade_all(engine, chain: Iterable[str]) -> None:
    for name in reversed(list(chain)):
        run_migration(engine, name, "downgrade")


def tables(engine) -> set:
    return set(sa.inspect(engine).get_table_names())


def columns(engine, table: str) -> set:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def schema_snapshot(engine) -> dict:
    insp = sa.inspect(engine)
    return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}
