from datetime import datetime, timedelta

import pytest

from app.models import Reading
from app.service import utcnow


def _insert_day(db, day: datetime, surges: list[float], base_level: float = 1.0) -> None:
    """Insert paired water_level/prediction rows producing the given surges."""
    for i, surge in enumerate(surges):
        ts = day + timedelta(hours=i)
        db.add(
            Reading(station_id="9414290", product="water_level", ts=ts, value=base_level + surge)
        )
        db.add(Reading(station_id="9414290", product="predictions", ts=ts, value=base_level))
    db.commit()


def test_history_aggregates_daily_surge(client, db):
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    _insert_day(db, yesterday, [0.1, 0.2, 0.3])
    _insert_day(db, today, [-0.1, 0.5])
    # an unpaired observation (no prediction at that ts) must not be counted
    db.add(
        Reading(
            station_id="9414290",
            product="water_level",
            ts=today + timedelta(hours=10),
            value=9.9,
        )
    )
    db.commit()

    resp = client.get("/api/stations/9414290/history?days=7")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    first, second = rows
    assert first["day"] == yesterday.date().isoformat()
    assert first["avg_surge"] == pytest.approx(0.2)
    assert first["max_surge"] == pytest.approx(0.3)
    assert first["samples"] == 3
    assert second["avg_surge"] == pytest.approx(0.2)
    assert second["max_surge"] == pytest.approx(0.5)
    assert second["samples"] == 2


def test_history_respects_days_window(client, db):
    old = utcnow() - timedelta(days=40)
    _insert_day(db, old.replace(hour=0, minute=0, second=0, microsecond=0), [1.0])

    assert client.get("/api/stations/9414290/history?days=30").json() == []
    assert len(client.get("/api/stations/9414290/history?days=60").json()) == 1


def test_history_validation_and_unknown_station(client):
    assert client.get("/api/stations/9414290/history?days=0").status_code == 422
    assert client.get("/api/stations/9414290/history?days=400").status_code == 422
    assert client.get("/api/stations/0000000/history").status_code == 404
