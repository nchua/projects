"""
Pytest fixtures for fitness app backend tests.

Provides shared fixtures for:
- In-memory SQLite database (session-scoped, shared per-worker)
- Per-test transaction rollback for isolation (xdist-safe)
- FastAPI TestClient bound to the test session
- Test users and auth headers
- Mock models + sample fixtures for pure-logic unit tests
"""
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from unittest.mock import MagicMock, Mock

import pytest

# Set test environment variables BEFORE any app imports.
# Use an in-memory SQLite shared across connections via StaticPool; this is
# xdist-safe (each worker gets its own process + its own in-memory DB) and
# leaves no stale `.test.db` file between runs.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 — register all models with Base.metadata
from app.core import database as _database
from app.core.database import Base, get_db
from app.core.security import hash_password

# Build our own in-memory engine with StaticPool so every connection sees the
# same underlying DB (default :memory: gives each connection its own DB).
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Monkey-patch the app's engine + SessionLocal so any code path that imports
# them directly (e.g. `from app.core.database import engine`) uses the test DB.
_database.engine = _test_engine
_database.SessionLocal = _TestSessionLocal


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    # pysqlite driver workaround: disable its auto-BEGIN emission so that
    # SQLAlchemy's explicit `BEGIN`/`ROLLBACK` actually takes effect.
    # Without this, pysqlite commits implicitly on DDL/DML boundaries and
    # the per-test outer `transaction.rollback()` below becomes a no-op,
    # leaking committed rows (e.g. users.email UNIQUE violations) across
    # tests. See https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl
    dbapi_connection.isolation_level = None


@event.listens_for(_test_engine, "begin")
def _sqlite_emit_begin(conn):
    # Pair with the isolation_level=None workaround above: we must emit
    # BEGIN ourselves now that pysqlite no longer does it for us.
    conn.exec_driver_sql("BEGIN")


# Import the app AFTER patching so main.py's startup migration fallback
# (Base.metadata.create_all(bind=engine)) targets our test engine.
from main import app as _app  # noqa: E402


@pytest.fixture(scope="session")
def _schema():
    """Create schema once per test session (per xdist worker)."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture
def db(_schema) -> Session:
    """
    Yield a Session wrapped in a SAVEPOINT-style transaction that is rolled
    back at the end of each test, giving full isolation without recreating
    the schema between tests.

    Uses SQLAlchemy 2.0's ``join_transaction_mode="create_savepoint"`` so
    the session automatically begins a fresh SAVEPOINT on every
    ``session.commit()`` in the app code — no manual event listener needed.
    """
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session):
    """
    FastAPI TestClient wired to the test database session.

    Overrides the get_db dependency so all endpoints share the same
    session (and thus the same transaction) as the test.

    Also resets the slowapi rate-limit storage between tests so that
    sequential tests don't accidentally trip the per-IP auth rate limit.
    """
    def _override_get_db():
        try:
            yield db
        finally:
            pass  # session lifecycle managed by the db fixture

    _app.dependency_overrides[get_db] = _override_get_db

    # Reset rate limiter state between tests — TestClient reuses the same
    # client IP, so shared state would cause spurious 429s across tests.
    try:
        limiter = getattr(_app.state, "limiter", None)
        if limiter is not None:
            limiter.reset()
    except Exception:
        pass

    with TestClient(_app, raise_server_exceptions=False) as c:
        yield c
    _app.dependency_overrides.clear()


@pytest.fixture
def create_test_user(db: Session):
    """
    Factory fixture that creates a real User in the test DB.

    Returns (user, plain_password) tuple.
    """
    from app.models.user import User, UserProfile

    def _create(email: str = "hunter@example.com", password: str = "TestPass123!") -> Tuple:
        user = User(
            email=email,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create default profile
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.commit()

        return user, password

    return _create


@pytest.fixture
def auth_headers(client: TestClient, create_test_user):
    """
    Factory fixture that creates a user, logs in, and returns auth headers.

    Returns (headers_dict, user) tuple.
    """
    def _auth(email: str = "hunter@example.com", password: str = "TestPass123!") -> Tuple:
        user, pwd = create_test_user(email=email, password=password)
        response = client.post("/auth/login", json={"email": email, "password": pwd})
        assert response.status_code == 200, f"Login failed: {response.json()}"
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, user

    return _auth


@pytest.fixture
def unique_email():
    """
    Factory fixture that returns a unique email per invocation.

    Use this in any test that creates users and might collide with another
    test's hardcoded email (especially under pytest-xdist parallelism).

    Example:
        def test_foo(unique_email, auth_headers):
            headers, user = auth_headers(email=unique_email("alice"))
    """
    def _make(prefix: str = "test") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"

    return _make


@pytest.fixture
def deleted_user(db: Session):
    """Create a user with is_deleted=True."""
    from app.models.user import User, UserProfile

    user = User(
        email="deleted@example.com",
        password_hash=hash_password("TestPass123!"),
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = UserProfile(user_id=user.id)
    db.add(profile)
    db.commit()

    return user


# ============ Screenshot / scan-credit scaffolding ============
#
# Shared by tests/test_screenshot_e2e.py, tests/test_screenshot_batch.py and
# tests/test_scan_balance_api.py. Mirrors the private helpers in
# tests/test_scan_credit_transaction.py so that file can adopt these later.


def make_png_bytes() -> bytes:
    """Return a minimal valid PNG (1x1 transparent pixel, 67 bytes)."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c636000010000000500010d0a2db40000000049454e"
        "44ae426082"
    )


@pytest.fixture
def png_bytes() -> bytes:
    """Minimal valid PNG bytes — passes UploadFile checks and magic-byte sniffing."""
    return make_png_bytes()


@pytest.fixture
def anthropic_api_key(monkeypatch):
    """Set a dummy API key so extract_workout_from_screenshot doesn't bail."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture
def mock_anthropic():
    """
    Factory that builds a mocked ``anthropic.Anthropic`` constructor.

    Each argument is one ``messages.create()`` outcome, in call order:
    - dict — JSON-encoded and wrapped in a Claude message mock
    - str  — used verbatim as the response text (e.g. malformed JSON)
    - Exception instance — raised by that call

    A single outcome repeats for every call. Patch the returned mock over
    ``app.services.screenshot_service.anthropic.Anthropic``; the client
    instance is available as ``ctor.return_value``.
    """
    def _to_message(payload) -> MagicMock:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        message = MagicMock()
        message.content = [MagicMock(text=text)]
        return message

    def _build(*payloads) -> MagicMock:
        client = MagicMock()
        if len(payloads) == 1 and not isinstance(payloads[0], BaseException):
            client.messages.create.return_value = _to_message(payloads[0])
        elif len(payloads) == 1:
            client.messages.create.side_effect = payloads[0]
        else:
            client.messages.create.side_effect = [
                p if isinstance(p, BaseException) else _to_message(p)
                for p in payloads
            ]
        return MagicMock(return_value=client)

    return _build


@pytest.fixture
def seed_scan_balance(db: Session):
    """Factory: create a ScanBalance row for a user."""
    from app.models.scan_balance import ScanBalance

    def _seed(
        user_id: str,
        credits: int = 3,
        has_unlimited: bool = False,
        free_scans_reset_at: Optional[datetime] = None,
    ) -> ScanBalance:
        kwargs = {}
        if free_scans_reset_at is not None:
            kwargs["free_scans_reset_at"] = free_scans_reset_at
        balance = ScanBalance(
            user_id=user_id,
            scan_credits=credits,
            has_unlimited=has_unlimited,
            **kwargs,
        )
        db.add(balance)
        db.commit()
        db.refresh(balance)
        return balance

    return _seed


@pytest.fixture
def seeded_exercises(db: Session):
    """Seed the exercise library from EXERCISES_DATA. Needed for fuzzy matching."""
    from app.api.exercises import EXERCISES_DATA
    from app.models.exercise import Exercise

    for ex_data in EXERCISES_DATA:
        ex = Exercise(
            id=str(uuid.uuid4()),
            name=ex_data["name"],
            canonical_id=str(uuid.uuid4()),
            category=ex_data["category"],
            primary_muscle=ex_data["primary_muscle"],
            secondary_muscles=ex_data["secondary_muscles"],
            is_custom=False,
            user_id=None,
        )
        db.add(ex)
    db.commit()
    return db


# ============ Mock Models ============

class MockExercise:
    """Mock Exercise model for testing"""
    def __init__(self, id: str, name: str, category: str = "compound"):
        self.id = id
        self.name = name
        self.category = category


class MockGoal:
    """Mock Goal model for testing"""
    def __init__(
        self,
        id: str,
        user_id: str,
        exercise_id: str,
        exercise: MockExercise,
        target_weight: float,
        target_reps: int = 1,
        weight_unit: str = "lb",
        deadline: date = None,
        status: str = "active",
        starting_e1rm: float = None,
        current_e1rm: float = None,
    ):
        self.id = id
        self.user_id = user_id
        self.exercise_id = exercise_id
        self.exercise = exercise
        self.target_weight = target_weight
        self.target_reps = target_reps
        self.weight_unit = weight_unit
        self.deadline = deadline or (date.today() + timedelta(weeks=12))
        self.status = status
        self.starting_e1rm = starting_e1rm
        self.current_e1rm = current_e1rm
        self.created_at = datetime.now(timezone.utc)
        self.achieved_at = None
        self.abandoned_at = None
        self.notes = None


# ============ Fixtures ============

@pytest.fixture
def test_user_id():
    """Return a test user ID"""
    return "test-user-1"


@pytest.fixture
def test_exercises():
    """
    Create standard exercises for testing.

    Returns dict with canonical names as keys:
    - bench_press: Barbell Bench Press
    - incline_bench: Incline Bench Press
    - dumbbell_bench: Dumbbell Bench Press
    - squat: Barbell Back Squat
    - front_squat: Front Squat
    - leg_press: Leg Press
    - deadlift: Barbell Deadlift
    - rdl: Romanian Deadlift
    - sumo_deadlift: Sumo Deadlift
    - row: Barbell Row
    """
    exercises = {
        # Bench Press variations
        "bench_press": MockExercise("ex-bench-001", "Barbell Bench Press", "compound"),
        "incline_bench": MockExercise("ex-bench-002", "Incline Bench Press", "compound"),
        "dumbbell_bench": MockExercise("ex-bench-003", "Dumbbell Bench Press", "compound"),

        # Squat variations
        "squat": MockExercise("ex-squat-001", "Barbell Back Squat", "compound"),
        "front_squat": MockExercise("ex-squat-002", "Front Squat", "compound"),
        "leg_press": MockExercise("ex-squat-003", "Leg Press", "compound"),

        # Deadlift variations
        "deadlift": MockExercise("ex-dead-001", "Barbell Deadlift", "compound"),
        "rdl": MockExercise("ex-dead-002", "Romanian Deadlift", "compound"),
        "sumo_deadlift": MockExercise("ex-dead-003", "Sumo Deadlift", "compound"),

        # Row variations
        "row": MockExercise("ex-row-001", "Barbell Row", "compound"),

        # Overhead Press
        "ohp": MockExercise("ex-ohp-001", "Overhead Press", "compound"),

        # Curl variations
        "curl": MockExercise("ex-curl-001", "Barbell Curl", "isolation"),
    }
    return exercises


@pytest.fixture
def mock_db_session(test_exercises):
    """
    Create a mock database session for testing.

    This mock provides basic query functionality for exercises.
    """
    db = Mock()

    # Setup exercise query
    def mock_exercise_query(*args, **kwargs):
        query_mock = Mock()

        # Chain .filter().first() to return exercise by ID
        def mock_filter(*filter_args, **filter_kwargs):
            filter_result = Mock()

            def mock_first():
                # Extract ID from filter args (simplified)
                for exercise in test_exercises.values():
                    return exercise  # Just return first for now
                return None

            filter_result.first = mock_first
            filter_result.all = lambda: list(test_exercises.values())
            return filter_result

        query_mock.filter = mock_filter
        query_mock.all = lambda: list(test_exercises.values())
        return query_mock

    db.query = mock_exercise_query
    db.add = Mock()
    db.commit = Mock()
    db.refresh = Mock()
    db.flush = Mock()

    return db


@pytest.fixture
def sample_goals(test_user_id, test_exercises):
    """
    Create sample goals for testing.

    Returns dict with:
    - bench_goal: 225 lb bench press goal
    - squat_goal: 315 lb squat goal
    - deadlift_goal: 405 lb deadlift goal
    """
    deadline = date.today() + timedelta(weeks=12)

    return {
        "bench_goal": MockGoal(
            id="goal-bench-001",
            user_id=test_user_id,
            exercise_id=test_exercises["bench_press"].id,
            exercise=test_exercises["bench_press"],
            target_weight=225,
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            starting_e1rm=200,
            current_e1rm=205,
        ),
        "squat_goal": MockGoal(
            id="goal-squat-001",
            user_id=test_user_id,
            exercise_id=test_exercises["squat"].id,
            exercise=test_exercises["squat"],
            target_weight=315,
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            starting_e1rm=280,
            current_e1rm=290,
        ),
        "deadlift_goal": MockGoal(
            id="goal-dead-001",
            user_id=test_user_id,
            exercise_id=test_exercises["deadlift"].id,
            exercise=test_exercises["deadlift"],
            target_weight=405,
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            starting_e1rm=365,
            current_e1rm=380,
        ),
    }


# ============ Helper Functions ============

def create_goal(
    user_id: str,
    exercise: MockExercise,
    target_weight: float,
    target_reps: int = 1,
    **kwargs
) -> MockGoal:
    """Helper to create a goal with defaults"""
    return MockGoal(
        id=kwargs.get("id", f"goal-{uuid.uuid4()}"),
        user_id=user_id,
        exercise_id=exercise.id,
        exercise=exercise,
        target_weight=target_weight,
        target_reps=target_reps,
        **{k: v for k, v in kwargs.items() if k not in ["id"]}
    )
