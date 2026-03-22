"""Custom SQLAlchemy types for cross-database compatibility."""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.types import TypeDecorator


class JSONB(TypeDecorator):
    """JSONB on PostgreSQL, JSON on other databases (e.g., SQLite for tests).

    This allows models to declare JSONB columns that work in both production
    (PostgreSQL) and tests (SQLite in-memory).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())
