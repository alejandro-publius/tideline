import os
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.noaa import NoaaClient
from app.routers.stations import get_noaa_client
from app.seed import seed_stations
from app.service import utcnow

NOAA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

# Point at a real database (e.g. postgres in CI) to run the suite against it;
# unset = fast in-memory SQLite.
TEST_DATABASE_URL = os.environ.get("TIDELINE_TEST_DATABASE_URL", "")


def water_level_payload(n: int = 10, base: float = 1.0) -> dict:
    """A NOAA water_level response with n readings, 6 minutes apart, ending now."""
    now = utcnow().replace(second=0, microsecond=0)
    rows = [
        {
            "t": (now - timedelta(minutes=6 * (n - 1 - i))).strftime("%Y-%m-%d %H:%M"),
            "v": f"{base + 0.01 * i:.3f}",
            "s": "0.050",
            "f": "0,0,0,0",
            "q": "p",
        }
        for i in range(n)
    ]
    return {
        "metadata": {"id": "9414290", "name": "San Francisco", "lat": "37.8", "lon": "-122.5"},
        "data": rows,
    }


def predictions_payload(hours_back: int = 2, hours_ahead: int = 2) -> dict:
    """A NOAA predictions response spanning past and future, hourly."""
    now = utcnow().replace(second=0, microsecond=0)
    rows = [
        {"t": (now + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M"), "v": f"{1.5 + 0.1 * h:.3f}"}
        for h in range(-hours_back, hours_ahead + 1)
    ]
    return {"predictions": rows}


@pytest.fixture()
def session_factory():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(engine)  # clean slate when reusing a real database
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        seed_stations(db)
    yield factory
    engine.dispose()


@pytest.fixture()
def db(session_factory):
    with session_factory() as session:
        yield session


def _no_retry_client() -> NoaaClient:
    """App NOAA client with retries and memoization disabled, so endpoint tests
    stay deterministic and never sleep on backoff. Retry/backoff/caching are
    covered directly in test_noaa_client."""
    return NoaaClient(get_settings().noaa_base_url, max_retries=0, backoff_base=0, cache_ttl=0)


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_noaa_client] = _no_retry_client
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
