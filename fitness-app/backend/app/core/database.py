"""
Database connection and session management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Create database engine
# Handle SQLite vs PostgreSQL connection args
if "sqlite" in settings.DATABASE_URL:
    connect_args = {"check_same_thread": False}
else:
    # PostgreSQL (Supabase, Railway, etc.)
    connect_args = {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # Handle connection drops
    pool_recycle=300,    # Recycle connections every 5 min
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy models
Base = declarative_base()


def get_db():
    """
    Dependency for getting database session
    Usage in FastAPI endpoints: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def mark_read_only(db: Session) -> None:
    """Make the rest of this transaction read-only where the dialect supports it.

    Postgres allows switching a transaction *to* read-only at any point (only
    the reverse is restricted), so this is safe after earlier reads in the
    same request. No-op on SQLite. Any accidental write then fails loudly
    instead of silently persisting.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL transaction_read_only = on"))
