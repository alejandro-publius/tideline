"""Unit tests for the MCP tool logic (the `_*` helpers), driven against a test
database session. The FastMCP wrappers are thin — they just open a session and
delegate — so exercising the helpers covers the behavior agents actually see."""

from datetime import timedelta

import pytest

from app.mcp_server import _list_stations, _station_surge, _surge_history, _surge_overview
from app.models import Reading
from app.service import utcnow


def _seed_reading(db, station_id, observed, predicted, minutes_ago=0):
    ts = (utcnow() - timedelta(minutes=minutes_ago)).replace(second=0, microsecond=0)
    db.add(Reading(station_id=station_id, product="water_level", ts=ts, value=observed))
    db.add(Reading(station_id=station_id, product="predictions", ts=ts, value=predicted))
    db.commit()
    return ts


def test_list_stations_returns_seeded_stations(db):
    stations = _list_stations(db)
    assert len(stations) >= 1
    sf = next(s for s in stations if s["id"] == "9414290")
    assert sf["name"] == "San Francisco"
    assert set(sf) == {"id", "name", "state", "lat", "lon", "flood_minor_m"}


def test_station_surge_reports_latest_reading(db):
    _seed_reading(db, "9414290", observed=1.25, predicted=1.0)
    result = _station_surge(db, "9414290")
    assert result["available"] is True
    assert result["observed_m"] == 1.25
    assert result["predicted_m"] == 1.0
    assert result["surge_m"] == pytest.approx(0.25)
    assert result["as_of"].endswith("Z")


def test_station_surge_marks_unavailable_when_no_recent_data(db):
    result = _station_surge(db, "9414290")
    assert result["available"] is False


def test_station_surge_rejects_unknown_station(db):
    with pytest.raises(ValueError, match="Unknown station"):
        _station_surge(db, "0000000")


def test_surge_overview_sorts_most_anomalous_first(db):
    _seed_reading(db, "9414290", observed=1.05, predicted=1.0)  # +0.05
    _seed_reading(db, "9410230", observed=2.5, predicted=1.0)  # +1.50, most anomalous
    overview = _surge_overview(db)
    rated = [r for r in overview if r["surge_m"] is not None]
    assert rated[0]["station_id"] == "9410230"
    # descending by absolute surge
    magnitudes = [abs(r["surge_m"]) for r in rated]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_surge_history_aggregates_and_clamps_days(db):
    yesterday = utcnow() - timedelta(days=1)
    for hours, (obs, pred) in enumerate([(1.1, 1.0), (1.3, 1.0)]):
        ts = yesterday.replace(hour=hours, minute=0, second=0, microsecond=0)
        db.add(Reading(station_id="9414290", product="water_level", ts=ts, value=obs))
        db.add(Reading(station_id="9414290", product="predictions", ts=ts, value=pred))
    db.commit()

    result = _surge_history(db, "9414290", days=1000)  # over the max
    assert result["days"] == 365  # clamped
    day = result["daily"][0]
    assert day["avg_surge_m"] == pytest.approx(0.2)
    assert day["max_surge_m"] == pytest.approx(0.3)
    assert day["samples"] == 2


def test_surge_history_rejects_unknown_station(db):
    with pytest.raises(ValueError, match="Unknown station"):
        _surge_history(db, "0000000", days=30)
