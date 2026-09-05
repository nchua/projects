"""ARISE v3 foundations (0a) — Campaign, load, coach tables + column additions

New tables: campaigns, campaign_arcs, hunt_templates, planned_hunts (spec
§4.2), daily_training_load (§6.2), coach_outputs (§8.5).

Column additions: goals gain the Objectives fields (§4.6) and exercise_id
becomes nullable (run objectives have no exercise); pr_gates gain family_id
and planned_hunt_id (§10.3); user_profiles gain injury_notes (§8.2) and
run_hr_cap_bpm (§5.2).

Idempotent: every create/add/alter is inspector-guarded. The NOT NULL drop on
goals.exercise_id is Postgres-only (SQLite test DBs follow the model via
create_all). quest_definitions / user_quests / user_directives are NOT
dropped here — that is Phase 4.

Revision ID: v3_campaign_tables
Revises: v3_exercise_families
Create Date: 2026-09-05

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'v3_campaign_tables'
down_revision = 'v3_exercise_families'
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _columns(table: str) -> dict:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {ix["name"] for ix in _inspector().get_indexes(table)}


def _dialect() -> str:
    return op.get_bind().dialect.name


def _batch_kwargs() -> dict:
    # SQLite must recreate to pick up inline FKs; Postgres runs plain ALTERs.
    return {"recreate": "always"} if _dialect() == "sqlite" else {}


# ── tables ──────────────────────────────────────────────────────────────────

def _create_tables():
    if not _has_table("campaigns"):
        op.create_table(
            "campaigns",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("goal", sa.Text(), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("source", sa.String(), nullable=False, server_default="import"),
            sa.Column("overrides", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Index("ix_campaigns_user_id", "user_id"),
        )

    if not _has_table("campaign_arcs"):
        op.create_table(
            "campaign_arcs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("index", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("weeks", sa.Integer(), nullable=False),
            sa.Column("run_miles_min", sa.Float(), nullable=True),
            sa.Column("run_miles_max", sa.Float(), nullable=True),
            sa.Column("long_run_miles", sa.Float(), nullable=True),
            sa.Column("deload_every_n_weeks", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("deload_factor", sa.Float(), nullable=False, server_default="0.75"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Index("ix_campaign_arcs_campaign_id", "campaign_id"),
        )

    if not _has_table("hunt_templates"):
        op.create_table(
            "hunt_templates",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "arc_id",
                sa.String(),
                sa.ForeignKey("campaign_arcs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("weekday", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("location_tag", sa.String(), nullable=True),
            sa.Column("load_hint", sa.Integer(), nullable=True),
            sa.Column("items", sa.JSON(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Index("ix_hunt_templates_arc_id", "arc_id"),
        )

    if not _has_table("planned_hunts"):
        op.create_table(
            "planned_hunts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "arc_id",
                sa.String(),
                sa.ForeignKey("campaign_arcs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "template_id",
                sa.String(),
                sa.ForeignKey("hunt_templates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("week_start", sa.Date(), nullable=False),
            sa.Column("week_target_miles", sa.Float(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="planned"),
            sa.Column(
                "session_id",
                sa.String(),
                sa.ForeignKey("workout_sessions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("moved_to", sa.Date(), nullable=True),
            sa.Column("prescription", sa.JSON(), nullable=True),
            sa.Column("prescription_version", sa.Integer(), nullable=True),
            sa.Column("generated_at", sa.DateTime(), nullable=True),
            sa.Column("rationale", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "user_id", "date", "template_id", name="uq_planned_hunts_user_date_template"
            ),
            sa.Index("ix_planned_hunts_user_id", "user_id"),
            sa.Index("ix_planned_hunts_campaign_id", "campaign_id"),
            sa.Index("ix_planned_hunts_date", "date"),
        )

    if not _has_table("daily_training_load"):
        op.create_table(
            "daily_training_load",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("local_date", sa.Date(), nullable=False),
            sa.Column("run_load", sa.Float(), nullable=False, server_default="0"),
            sa.Column("lift_load", sa.Float(), nullable=False, server_default="0"),
            sa.Column("total_load", sa.Float(), nullable=False, server_default="0"),
            sa.Column("miles", sa.Float(), nullable=False, server_default="0"),
            sa.Column("run_acute_7d", sa.Float(), nullable=True),
            sa.Column("run_chronic_28d", sa.Float(), nullable=True),
            sa.Column("run_acwr", sa.Float(), nullable=True),
            sa.Column("total_acute_7d", sa.Float(), nullable=True),
            sa.Column("total_chronic_28d", sa.Float(), nullable=True),
            sa.Column("total_acwr", sa.Float(), nullable=True),
            sa.Column("miles_7d", sa.Float(), nullable=False, server_default="0"),
            sa.Column("miles_plan_7d", sa.Float(), nullable=True),
            sa.Column("longest_run_7d", sa.Float(), nullable=False, server_default="0"),
            sa.Column("flags", sa.JSON(), nullable=False),
            sa.Column("computed_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "local_date", name="uq_daily_training_load_user_date"),
            sa.Index("ix_daily_training_load_user_id", "user_id"),
        )

    if not _has_table("coach_outputs"):
        op.create_table(
            "coach_outputs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("for_date", sa.Date(), nullable=False),
            sa.Column("context_hash", sa.String(), nullable=False),
            sa.Column("prompt_version", sa.String(), nullable=False),
            sa.Column("model", sa.String(), nullable=False),
            sa.Column("output", sa.JSON(), nullable=True),
            sa.Column("validated", sa.JSON(), nullable=True),
            sa.Column("decisions", sa.JSON(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="model"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "kind", "for_date", name="uq_coach_outputs_user_kind_date"),
            sa.Index("ix_coach_outputs_user_id", "user_id"),
        )


# ── column additions ────────────────────────────────────────────────────────

def _alter_goals():
    cols = _columns("goals")
    if "campaign_id" not in cols:
        with op.batch_alter_table("goals", **_batch_kwargs()) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "campaign_id",
                    sa.String(),
                    sa.ForeignKey("campaigns.id", name="fk_goals_campaign_id"),
                    nullable=True,
                )
            )
    if "kind" not in cols:
        op.add_column(
            "goals",
            sa.Column("kind", sa.String(), nullable=False, server_default="strength"),
        )
    if "target_miles" not in cols:
        op.add_column("goals", sa.Column("target_miles", sa.Float(), nullable=True))
    if "run_scope" not in cols:
        op.add_column("goals", sa.Column("run_scope", sa.String(), nullable=True))
    if "deadline_extensions" not in cols:
        op.add_column(
            "goals",
            sa.Column("deadline_extensions", sa.Integer(), nullable=False, server_default="0"),
        )
    # Run objectives have no exercise. Postgres-only: SQLite cannot ALTER
    # COLUMN and its test schema comes from create_all (already nullable).
    if _dialect() == "postgresql" and not cols["exercise_id"]["nullable"]:
        op.alter_column("goals", "exercise_id", existing_type=sa.String(), nullable=True)


def _alter_pr_gates():
    cols = _columns("pr_gates")
    if "family_id" not in cols or "planned_hunt_id" not in cols:
        with op.batch_alter_table("pr_gates", **_batch_kwargs()) as batch_op:
            if "family_id" not in cols:
                batch_op.add_column(
                    sa.Column(
                        "family_id",
                        sa.String(),
                        sa.ForeignKey("exercise_families.id", name="fk_pr_gates_family_id"),
                        nullable=True,
                    )
                )
            if "planned_hunt_id" not in cols:
                batch_op.add_column(
                    sa.Column(
                        "planned_hunt_id",
                        sa.String(),
                        sa.ForeignKey("planned_hunts.id", name="fk_pr_gates_planned_hunt_id"),
                        nullable=True,
                    )
                )


def _alter_user_profiles():
    cols = _columns("user_profiles")
    if "injury_notes" not in cols:
        op.add_column("user_profiles", sa.Column("injury_notes", sa.Text(), nullable=True))
    if "run_hr_cap_bpm" not in cols:
        op.add_column("user_profiles", sa.Column("run_hr_cap_bpm", sa.Integer(), nullable=True))


def upgrade():
    _create_tables()
    _alter_goals()
    _alter_pr_gates()
    _alter_user_profiles()


def downgrade():
    cols = _columns("user_profiles")
    with op.batch_alter_table("user_profiles") as batch_op:
        for col in ("run_hr_cap_bpm", "injury_notes"):
            if col in cols:
                batch_op.drop_column(col)

    cols = _columns("pr_gates")
    with op.batch_alter_table("pr_gates") as batch_op:
        for col in ("planned_hunt_id", "family_id"):
            if col in cols:
                batch_op.drop_column(col)

    cols = _columns("goals")
    with op.batch_alter_table("goals") as batch_op:
        for col in ("deadline_extensions", "run_scope", "target_miles", "kind", "campaign_id"):
            if col in cols:
                batch_op.drop_column(col)
    if _dialect() == "postgresql" and cols["exercise_id"]["nullable"]:
        # Only restore NOT NULL when no run objective would violate it.
        null_rows = op.get_bind().execute(
            sa.text("SELECT count(*) FROM goals WHERE exercise_id IS NULL")
        ).scalar()
        if not null_rows:
            op.alter_column("goals", "exercise_id", existing_type=sa.String(), nullable=False)

    for table in (
        "coach_outputs",
        "daily_training_load",
        "planned_hunts",
        "hunt_templates",
        "campaign_arcs",
        "campaigns",
    ):
        if _has_table(table):
            op.drop_table(table)
