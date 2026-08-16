"""Shared fixtures: in-memory DB per test, TestClient with overridden session."""
import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models.app_state import AppState
from app.models.region import DriveTime, Region
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def seeded(db_session):
    """Minimal reference data: three regions and their drive-time triangle."""
    db_session.add_all(
        [
            Region(id="WAI", name="Waikiki", sort_order=0, tour_order=0),
            Region(id="EAST", name="East Coast", sort_order=1, tour_order=7),
            Region(id="NS", name="North Shore", sort_order=2, tour_order=4),
            DriveTime(region_a="EAST", region_b="WAI", minutes=25, flags=""),
            DriveTime(region_a="NS", region_b="WAI", minutes=60, flags="H1_PM"),
            DriveTime(region_a="EAST", region_b="NS", minutes=80, flags=""),
            DriveTime(region_a="WAI", region_b="WAI", minutes=10, flags=""),
            DriveTime(region_a="EAST", region_b="EAST", minutes=10, flags=""),
            DriveTime(region_a="NS", region_b="NS", minutes=10, flags=""),
            AppState(id=1, version=1),
        ]
    )
    db_session.commit()
    return db_session
