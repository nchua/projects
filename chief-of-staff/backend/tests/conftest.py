"""Test fixtures and configuration."""

import os

os.environ["TESTING"] = "1"

# Ensure a dummy encryption key exists for tests that exercise OAuth endpoints
if not os.environ.get("TOKEN_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db  # noqa: E402
from app.core.encryption import _get_fernet  # noqa: E402
import app.models  # noqa: F401,E402 — register all models before create_all


@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite engine for tests."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable foreign keys in SQLite
    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture(autouse=True)
def _clear_fernet_cache():
    """Clear the Fernet cache before each test to prevent cross-test poisoning."""
    _get_fernet.cache_clear()
    yield
    _get_fernet.cache_clear()


@pytest.fixture
def db_session(engine):
    """Create a fresh database session for each test, rolled back after."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """Create a TestClient with the test database session."""
    from main import app

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
