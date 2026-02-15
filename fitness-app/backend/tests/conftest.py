"""
Pytest fixtures for fitness app backend tests.

Provides shared fixtures for:
- In-memory SQLite database (mock models for unit tests)
- Integration test database (real SQLAlchemy models + TestClient)
- Test users
- Test exercises (Big Three + variations)
"""
import os
import pytest
from datetime import date, datetime, timedelta
from typing import List, Tuple
from unittest.mock import Mock, MagicMock
import uuid

# Set test environment variables BEFORE any app imports
_TEST_DB_PATH = os.path.join(os.path.dirname(__file__), ".test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

from sqlalchemy import event
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.core.database import Base, get_db, engine, SessionLocal
from app.core.security import hash_password, create_access_token
from app import models  # noqa: F401 — register all models with Base.metadata

# Import app once at module level; main.py runs migrations on import.
# Since DATABASE_URL points to a file-based SQLite, alembic may warn/fail
# but the fallback create_all(bind=engine) ensures tables exist.
from main import app as _app


# ============ Integration Test Infrastructure ============

# Enable foreign key support for SQLite on the app's engine
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db():
    """
    Create a fresh test database for each test.

    Drops and recreates all tables for isolation, yields a session.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session):
    """
    FastAPI TestClient wired to the test database session.

    Overrides the get_db dependency so all endpoints share the same
    session (and thus the same transaction) as the test.
    """
    def _override_get_db():
        try:
            yield db
        finally:
            pass  # session lifecycle managed by the db fixture

    _app.dependency_overrides[get_db] = _override_get_db
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
def deleted_user(db: Session):
    """Create a user with is_deleted=True."""
    from app.models.user import User, UserProfile

    user = User(
        email="deleted@example.com",
        password_hash=hash_password("TestPass123!"),
        is_deleted=True,
        deleted_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = UserProfile(user_id=user.id)
    db.add(profile)
    db.commit()

    return user


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
        self.created_at = datetime.utcnow()
        self.achieved_at = None
        self.abandoned_at = None
        self.notes = None


class MockSet:
    """Mock Set model for testing"""
    def __init__(self, weight: float, reps: int, rpe: int = None):
        self.weight = weight
        self.reps = reps
        self.rpe = rpe
        self.rir = None
        self.e1rm = weight * (1 + reps / 30)  # Epley formula


class MockWorkoutExercise:
    """Mock WorkoutExercise model for testing"""
    def __init__(self, exercise_id: str, exercise: MockExercise, sets: List[MockSet] = None):
        self.id = str(uuid.uuid4())
        self.exercise_id = exercise_id
        self.exercise = exercise
        self.sets = sets or []


class MockWorkoutSession:
    """Mock WorkoutSession model for testing"""
    def __init__(
        self,
        id: str = None,
        user_id: str = None,
        workout_exercises: List[MockWorkoutExercise] = None,
        workout_date: date = None,
    ):
        from datetime import date as date_type
        self.id = id or str(uuid.uuid4())
        self.user_id = user_id or "test-user-1"
        self.workout_exercises = workout_exercises or []
        self.date = workout_date or date_type.today()
        self.duration_minutes = 60


class MockMissionGoal:
    """Mock MissionGoal junction table entry"""
    def __init__(self, goal: MockGoal, workouts_completed: int = 0, is_satisfied: bool = False):
        self.id = str(uuid.uuid4())
        self.mission_id = None
        self.goal_id = goal.id
        self.goal = goal
        self.workouts_completed = workouts_completed
        self.is_satisfied = is_satisfied


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
def exercise_db(test_exercises):
    """
    Mock database query for exercises.
    Returns a function that simulates db.query(Exercise).filter(...).first()
    """
    def query_exercise_by_id(exercise_id: str) -> MockExercise:
        for exercise in test_exercises.values():
            if exercise.id == exercise_id:
                return exercise
        return None

    def query_all_exercises() -> List[MockExercise]:
        return list(test_exercises.values())

    # Return object with both methods
    class ExerciseDB:
        def get_by_id(self, exercise_id):
            return query_exercise_by_id(exercise_id)

        def get_all(self):
            return query_all_exercises()

    return ExerciseDB()


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


@pytest.fixture
def sample_workout(test_user_id, test_exercises):
    """
    Create a sample workout with bench and squat exercises.
    """
    bench = test_exercises["bench_press"]
    squat = test_exercises["squat"]

    bench_sets = [
        MockSet(185, 5),
        MockSet(205, 3),
        MockSet(225, 1),
    ]

    squat_sets = [
        MockSet(225, 5),
        MockSet(275, 3),
        MockSet(315, 1),
    ]

    workout = MockWorkoutSession(
        id="workout-001",
        user_id=test_user_id,
        workout_exercises=[
            MockWorkoutExercise(bench.id, bench, bench_sets),
            MockWorkoutExercise(squat.id, squat, squat_sets),
        ],
        date=date.today(),
    )

    return workout


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


def create_workout(
    user_id: str,
    exercises_with_sets: List[tuple],  # [(exercise, [(weight, reps), ...]), ...]
) -> MockWorkoutSession:
    """
    Helper to create a workout with exercises and sets.

    Args:
        user_id: User ID
        exercises_with_sets: List of (MockExercise, [(weight, reps), ...]) tuples

    Returns:
        MockWorkoutSession
    """
    workout_exercises = []
    for exercise, sets_data in exercises_with_sets:
        sets = [MockSet(weight, reps) for weight, reps in sets_data]
        workout_exercises.append(MockWorkoutExercise(exercise.id, exercise, sets))

    return MockWorkoutSession(
        user_id=user_id,
        workout_exercises=workout_exercises,
    )
