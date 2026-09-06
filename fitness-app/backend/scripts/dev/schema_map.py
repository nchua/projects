"""Print every table with its foreign keys (and ON DELETE), required columns, and enum columns.

Run from fitness-app/backend (no database needed — it reads the SQLAlchemy metadata):

    SECRET_KEY=x JWT_SECRET_KEY=x venv/bin/python scripts/dev/schema_map.py [table ...]

Answers, in one command, the questions a purge order, a seed helper, or a
new FK migration needs: what references ``users.id``, what cascades, and
which columns a row must carry (session-pickup cost, 2026-09-06).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("SECRET_KEY", "schema-map")
os.environ.setdefault("JWT_SECRET_KEY", "schema-map")

import app.models  # noqa: E402, F401 — register every model
from app.core.database import Base  # noqa: E402


def describe(table) -> str:
    fks = [
        f"{c.name} -> {fk.column.table.name}.{fk.column.name}" + (f" ON DELETE {fk.ondelete}" if fk.ondelete else "")
        for c in table.columns
        for fk in c.foreign_keys
    ]
    required = [
        c.name
        for c in table.columns
        if not c.nullable and c.default is None and c.server_default is None and not c.primary_key
    ]
    enums = [f"{c.name}: {type(c.type).__name__}" for c in table.columns if type(c.type).__name__ == "Enum"]
    lines = [f"{table.name}  ({len(table.columns)} cols)"]
    lines.append(f"  fks:      {fks or '-'}")
    lines.append(f"  required: {required or '-'}")
    if enums:
        lines.append(f"  enums:    {enums}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    wanted = set(argv)
    tables = [t for t in Base.metadata.sorted_tables if not wanted or t.name in wanted]
    for table in tables:
        print(describe(table))
    referencing = sorted(
        t.name for t in Base.metadata.tables.values()
        for c in t.columns for fk in c.foreign_keys if fk.column.table.name == "users"
    )
    if not wanted:
        print(f"\n{len(set(referencing))} tables reference users.id: {sorted(set(referencing))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
