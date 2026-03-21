"""Initial schema — all Phase 1 tables

Revision ID: 001
Revises:
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Shared enum definitions
CONCEPT_TIER = sa.Enum(
    "new", "learning", "reviewing", "mastered",
    name="concepttier",
)
EDGE_TYPE = sa.Enum(
    "prerequisite", "supports", "relates_to", "part_of",
    name="edgetype",
)
SOURCE_TYPE = sa.Enum(
    "gmail", "notion", "web", "blog", "manual", "obsidian",
    name="sourcetype",
)
UNIT_TYPE = sa.Enum(
    "concept", "cloze", "explanation",
    "application", "connection", "generative",
    name="unittype",
)
RATING = sa.Enum(
    "forgot", "struggled", "got_it", "easy",
    name="rating",
)
INBOX_STATUS = sa.Enum(
    "pending", "accepted", "rejected",
    name="inboxstatus",
)

TS = sa.DateTime(timezone=True)
NOW = sa.func.now()


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "email", sa.String(255),
            unique=True, nullable=False, index=True,
        ),
        sa.Column(
            "hashed_password", sa.String(255),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(100)),
        sa.Column("created_at", TS, server_default=NOW),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False, index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column(
            "target_retention", sa.Float(),
            server_default="0.9",
        ),
        sa.Column("created_at", TS, server_default=NOW),
    )

    op.create_table(
        "concepts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "topic_id", sa.Integer(),
            sa.ForeignKey("topics.id"),
            nullable=False, index=True,
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column(
            "mastery_score", sa.Float(),
            server_default="0.0",
        ),
        sa.Column(
            "tier", CONCEPT_TIER,
            server_default="new",
        ),
        sa.Column("created_at", TS, server_default=NOW),
    )

    op.create_table(
        "concept_relationships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_concept_id", sa.Integer(),
            sa.ForeignKey("concepts.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "target_concept_id", sa.Integer(),
            sa.ForeignKey("concepts.id"),
            nullable=False, index=True,
        ),
        sa.Column("edge_type", EDGE_TYPE, nullable=False),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False, index=True,
        ),
        sa.Column("type", SOURCE_TYPE, nullable=False),
        sa.Column("uri", sa.String(2000)),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("last_synced_at", TS),
        sa.Column("created_at", TS, server_default=NOW),
    )

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_id", sa.Integer(),
            sa.ForeignKey("sources.id"),
            nullable=False, index=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "chunk_index", sa.Integer(),
            server_default="0",
        ),
        sa.Column("created_at", TS, server_default=NOW),
    )

    op.execute(
        "ALTER TABLE source_documents "
        "ADD COLUMN embedding vector(1536)"
    )

    op.create_table(
        "learning_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "concept_id", sa.Integer(),
            sa.ForeignKey("concepts.id"),
            nullable=False, index=True,
        ),
        sa.Column("type", UNIT_TYPE, nullable=False),
        sa.Column(
            "front_content", sa.Text(), nullable=False,
        ),
        sa.Column(
            "back_content", sa.Text(), nullable=False,
        ),
        sa.Column(
            "difficulty", sa.Float(),
            server_default="0.3",
        ),
        sa.Column(
            "stability", sa.Float(),
            server_default="0.0",
        ),
        sa.Column(
            "retrievability", sa.Float(),
            server_default="1.0",
        ),
        sa.Column("last_reviewed_at", TS),
        sa.Column("next_review_at", TS, index=True),
        sa.Column(
            "review_count", sa.Integer(),
            server_default="0",
        ),
        sa.Column(
            "lapse_count", sa.Integer(),
            server_default="0",
        ),
        sa.Column(
            "source_id", sa.Integer(),
            sa.ForeignKey("sources.id"),
        ),
        sa.Column(
            "auto_accepted", sa.Boolean(),
            server_default="false",
        ),
        sa.Column(
            "ai_generated", sa.Boolean(),
            server_default="false",
        ),
        sa.Column("created_at", TS, server_default=NOW),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "learning_unit_id", sa.Integer(),
            sa.ForeignKey("learning_units.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False, index=True,
        ),
        sa.Column("rating", RATING, nullable=False),
        sa.Column("time_to_reveal_ms", sa.Integer()),
        sa.Column("time_reading_ms", sa.Integer()),
        sa.Column("reviewed_at", TS, server_default=NOW),
    )

    op.create_table(
        "inbox_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "learning_unit_id", sa.Integer(),
            sa.ForeignKey("learning_units.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "confidence_score", sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "status", INBOX_STATUS,
            server_default="pending",
        ),
        sa.Column("created_at", TS, server_default=NOW),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "agent_type", sa.String(100),
            nullable=False,
        ),
        sa.Column(
            "source_id", sa.Integer(),
            sa.ForeignKey("sources.id"),
        ),
        sa.Column(
            "units_generated", sa.Integer(),
            server_default="0",
        ),
        sa.Column("tokens_used", sa.Integer()),
        sa.Column("cost", sa.Float()),
        sa.Column(
            "started_at", TS, server_default=NOW,
        ),
        sa.Column("completed_at", TS),
    )


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("inbox_items")
    op.drop_table("reviews")
    op.drop_table("learning_units")
    op.drop_table("source_documents")
    op.drop_table("sources")
    op.drop_table("concept_relationships")
    op.drop_table("concepts")
    op.drop_table("topics")
    op.drop_table("users")

    for name in [
        "rating", "inboxstatus", "unittype",
        "sourcetype", "edgetype", "concepttier",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {name}")

    op.execute("DROP EXTENSION IF EXISTS vector")
