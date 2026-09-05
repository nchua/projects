"""ARISE v3 foundations (0a) — exercise_families + exercises.family_id

Creates the family table, seeds it from the committed dict in
``app/services/exercise_family_defs.py`` and assigns ``family_id`` to every
seeded (non-custom) exercise by canonical/alias name so prod is correct on
deploy without an owner script. Custom exercises are name-matched by
``scripts/backfill_exercise_families.py`` (and on creation).

Idempotent: table/column/index creation is inspector-guarded, family rows are
inserted only when missing, and the UPDATE only touches rows whose family_id
differs — a re-run is a no-op.

Revision ID: v3_exercise_families
Revises: v3_sets_columns
Create Date: 2026-09-05

"""
from collections import defaultdict

import sqlalchemy as sa

from alembic import op
from app.services.exercise_family_defs import FAMILY_DEFS, resolve_family_assignments

# revision identifiers, used by Alembic.
revision = 'v3_exercise_families'
down_revision = 'v3_sets_columns'
branch_labels = None
depends_on = None

FK_NAME = "fk_exercises_family_id"
INDEX_NAME = "ix_exercises_family_id"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {ix["name"] for ix in _inspector().get_indexes(table)}


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _seed_families(conn) -> int:
    existing = {r[0] for r in conn.execute(sa.text("SELECT id FROM exercise_families"))}
    families = sa.table(
        "exercise_families",
        sa.column("id", sa.String),
        sa.column("display_name", sa.String),
        sa.column("primary_muscle", sa.String),
        sa.column("is_big_three", sa.Boolean),
        sa.column("standards_key", sa.String),
        sa.column("increment_lb", sa.Float),
    )
    rows = [
        {
            "id": slug,
            "display_name": defn["display_name"],
            "primary_muscle": defn["primary_muscle"],
            "is_big_three": bool(defn["is_big_three"]),
            "standards_key": defn["standards_key"],
            "increment_lb": float(defn["increment_lb"]),
        }
        for slug, defn in FAMILY_DEFS.items()
        if slug not in existing
    ]
    if rows:
        op.bulk_insert(families, rows)
    return len(rows)


def _assign_family_ids(conn) -> int:
    """Set exercises.family_id for seeded rows from the committed dict."""
    rows = conn.execute(
        sa.text("SELECT id, name, canonical_id FROM exercises WHERE is_custom = false")
    ).fetchall()
    assignments = resolve_family_assignments((r[0], r[1], r[2]) for r in rows)

    by_family = defaultdict(list)
    for ex_id, fam in assignments.items():
        if fam:
            by_family[fam].append(ex_id)

    stmt = sa.text(
        "UPDATE exercises SET family_id = :fam "
        "WHERE id IN :ids AND (family_id IS NULL OR family_id <> :fam)"
    ).bindparams(sa.bindparam("ids", expanding=True))

    updated = 0
    for fam, ids in by_family.items():
        for start in range(0, len(ids), 500):
            result = conn.execute(stmt, {"fam": fam, "ids": ids[start:start + 500]})
            updated += result.rowcount or 0
    return updated


def upgrade():
    if not _has_table("exercise_families"):
        op.create_table(
            "exercise_families",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("display_name", sa.String(), nullable=False),
            sa.Column("primary_muscle", sa.String(), nullable=True),
            sa.Column("is_big_three", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("standards_key", sa.String(), nullable=True),
            sa.Column("increment_lb", sa.Float(), nullable=False, server_default="5.0"),
        )

    if not _has_column("exercises", "family_id"):
        # Batch mode so SQLite (tests) recreates the table with the FK inline;
        # Postgres runs the plain ALTER TABLE ADD COLUMN + ADD CONSTRAINT.
        with op.batch_alter_table(
            "exercises", recreate="always" if _sqlite() else "auto"
        ) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "family_id",
                    sa.String(),
                    sa.ForeignKey("exercise_families.id", name=FK_NAME),
                    nullable=True,
                )
            )
    if not _has_index("exercises", INDEX_NAME):
        op.create_index(INDEX_NAME, "exercises", ["family_id"])

    conn = op.get_bind()
    _seed_families(conn)
    _assign_family_ids(conn)


def downgrade():
    if _has_column("exercises", "family_id"):
        if _has_index("exercises", INDEX_NAME):
            op.drop_index(INDEX_NAME, table_name="exercises")
        with op.batch_alter_table("exercises") as batch_op:
            batch_op.drop_column("family_id")
    if _has_table("exercise_families"):
        op.drop_table("exercise_families")
