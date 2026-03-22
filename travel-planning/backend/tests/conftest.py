"""Shared test fixtures for Depart backend tests."""

from __future__ import annotations

import os

# Set environment variables BEFORE importing app modules.
# database.py creates a module-level engine at import time via get_settings().
# We use a dummy PostgreSQL URL here (never actually connects — get_db is
# overridden in all tests). SQLite can't accept pool_size/max_overflow args.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models.enums import AuthProvider, TravelMode, TripStatus
from app.models.trip import Trip
from app.models.user import User

# ---------------------------------------------------------------------------
# Test database engine (SQLite in-memory, async)
# ---------------------------------------------------------------------------
# Use shared-cache in-memory DB with NullPool so multiple concurrent
# connections (fixture session + app/worker session) can access the same data
# without SQLite blocking on single-connection StaticPool.

TEST_DB_URL = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"

test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@event.listens_for(test_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    """Enable SQLite foreign key enforcement."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

TEST_USER_ID = uuid.UUID("12345678-1234-1234-1234-123456789abc")
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "TestPass123!"


def _patch_jsonb_columns() -> None:
    """Replace JSONB column types with JSON so SQLite can create them."""
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create tables, yield a session, then drop tables.

    A "holding" connection is kept open for the duration of the test so the
    shared-cache in-memory SQLite database isn't destroyed when NullPool
    closes individual connections.
    """
    _patch_jsonb_columns()

    # Keep one connection alive so the in-memory DB persists across NullPool
    # connections (SQLite drops a shared-cache DB when the last conn closes).
    holding_conn = await test_engine.connect()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await holding_conn.close()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Insert and return a test user."""
    user = User(
        id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        password_hash=hash_password(TEST_USER_PASSWORD),
        display_name="Test User",
        auth_provider=AuthProvider.email,
        default_buffer_minutes=15,
        default_travel_mode=TravelMode.driving,
        timezone="America/Los_Angeles",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def second_user(db_session: AsyncSession) -> User:
    """Insert and return a second test user (for ownership tests)."""
    user = User(
        id=uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        email="other@example.com",
        password_hash=hash_password("OtherPass123!"),
        display_name="Other User",
        auth_provider=AuthProvider.email,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(
    db_session: AsyncSession,
    test_user: User,
) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with auth and DB dependency overrides."""
    from main import app

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def unauth_client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client WITHOUT auth override (for 401 tests)."""
    from main import app

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    # Do NOT override get_current_user -> real JWT check runs

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: create a trip in the DB
# ---------------------------------------------------------------------------


@pytest.fixture
def make_trip(db_session: AsyncSession, test_user: User):
    """Factory fixture that creates a Trip in the test DB."""

    async def _make(
        *,
        name: str = "Test Trip",
        arrival_hours_from_now: float = 2.0,
        buffer_minutes: int = 15,
        status: TripStatus = TripStatus.pending,
        origin_address: str = "123 Home St",
        origin_lat: float = 37.7749,
        origin_lng: float = -122.4194,
        dest_address: str = "456 Office Ave",
        dest_lat: float = 37.3382,
        dest_lng: float = -121.8863,
        user: User | None = None,
    ) -> Trip:
        now = datetime.now(timezone.utc)
        arrival = now + timedelta(hours=arrival_hours_from_now)
        notify_at = arrival - timedelta(minutes=buffer_minutes)

        trip = Trip(
            user_id=(user or test_user).id,
            name=name,
            origin_address=origin_address,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_address=dest_address,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            arrival_time=arrival,
            travel_mode=TravelMode.driving,
            buffer_minutes=buffer_minutes,
            status=status,
            notify_at=notify_at,
        )
        db_session.add(trip)
        await db_session.commit()
        await db_session.refresh(trip)
        return trip

    return _make
