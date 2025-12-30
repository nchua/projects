"""Pytest fixtures for strength coach tests."""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile

from strength_coach.models import (
    BodyWeightEntry,
    ExercisePerformance,
    SetRecord,
    WeightUnit,
    WorkoutSession,
)
from strength_coach.storage import SQLiteStorage


@pytest.fixture
def sample_sets() -> list[SetRecord]:
    """Sample sets for testing."""
    return [
        SetRecord(reps=5, weight=Decimal("225"), weight_unit=WeightUnit.LB, rir=2),
        SetRecord(reps=5, weight=Decimal("225"), weight_unit=WeightUnit.LB, rir=2),
        SetRecord(reps=5, weight=Decimal("225"), weight_unit=WeightUnit.LB, rir=1),
    ]


@pytest.fixture
def sample_exercise(sample_sets) -> ExercisePerformance:
    """Sample exercise performance."""
    return ExercisePerformance(
        exercise_name="Squat",
        canonical_id="squat",
        sets=sample_sets,
    )


@pytest.fixture
def sample_session(sample_exercise) -> WorkoutSession:
    """Sample workout session."""
    return WorkoutSession(
        date=date.today(),
        exercises=[sample_exercise],
        session_rpe=7.5,
        notes="Test session",
    )


@pytest.fixture
def sample_bodyweight_entries() -> list[BodyWeightEntry]:
    """Sample body weight entries over 2 weeks."""
    entries = []
    base_date = date.today() - timedelta(days=14)
    weights = [166.0, 165.8, 166.2, 165.5, 166.0, 165.6, 165.8,
               165.5, 165.4, 165.6, 165.2, 165.4, 165.0, 165.2, 165.0]

    for i, weight in enumerate(weights):
        entries.append(
            BodyWeightEntry(
                date=base_date + timedelta(days=i),
                weight=Decimal(str(weight)),
                weight_unit=WeightUnit.LB,
            )
        )
    return entries


@pytest.fixture
def temp_db() -> Path:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def storage(temp_db) -> SQLiteStorage:
    """Create a storage instance with temp database."""
    store = SQLiteStorage(temp_db)
    yield store
    store.close()


@pytest.fixture
def populated_storage(storage, sample_session, sample_bodyweight_entries) -> SQLiteStorage:
    """Storage with sample data."""
    storage.save_session(sample_session)
    for entry in sample_bodyweight_entries:
        storage.save_bodyweight(entry)
    return storage
