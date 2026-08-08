"""Detector tests (ADR 0007).

The message-handling logic is deliberately separated from the pika consume loop
so it can be tested against a real database with no broker running. What is
worth pinning here is the verdict logic and what reaches the anomalies table.
"""

import json
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, make_engine
from app.detector import evaluate, handle_message
from app.models import Anomaly, Station


@pytest.fixture
def db() -> Session:
    engine = make_engine("sqlite://")  # in-memory
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Station(
                id="9414290",
                name="San Francisco",
                state="CA",
                lat=37.8,
                lon=-122.5,
                flood_minor=1.1,
                flood_moderate=1.3,
                flood_major=1.5,
            )
        )
        session.commit()
        yield session


def _event(value: float, product: str = "water_level", station: str = "9414290") -> bytes:
    return json.dumps(
        {
            "station_id": station,
            "product": product,
            "ts": "2026-08-08T12:00:00",
            "value": value,
        }
    ).encode()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.9, None),  # below every threshold
        (1.1, "minor"),  # exactly at minor — thresholds are inclusive
        (1.2, "minor"),
        (1.3, "moderate"),
        (1.6, "major"),
    ],
)
def test_evaluate_maps_levels_to_severity(db: Session, value: float, expected: str | None) -> None:
    assert evaluate(db, "9414290", "water_level", datetime(2026, 8, 8, 12, 0), value) == expected


def test_only_water_level_is_evaluated(db: Session) -> None:
    """A prediction is not an observation; it must not raise a flood anomaly."""
    assert evaluate(db, "9414290", "predictions", datetime(2026, 8, 8, 12, 0), 9.9) is None


def test_unknown_station_yields_no_verdict(db: Session) -> None:
    """No thresholds means no judgement — and, importantly, no exception.

    Raising here would leave the message unacknowledged and redelivered forever.
    """
    assert evaluate(db, "nope", "water_level", datetime(2026, 8, 8, 12, 0), 99.0) is None


def test_handle_message_records_a_crossing(db: Session) -> None:
    handle_message(db, _event(1.4))

    rows = db.scalars(select(Anomaly)).all()
    assert len(rows) == 1
    assert rows[0].severity == "moderate"
    assert rows[0].value == 1.4
    assert rows[0].station_id == "9414290"


def test_handle_message_records_nothing_when_clear(db: Session) -> None:
    handle_message(db, _event(0.5))

    assert db.scalars(select(Anomaly)).all() == []
