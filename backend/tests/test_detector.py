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
from app.models import Anomaly, Reading, Station


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


TS = datetime(2026, 8, 8, 12, 0)


def _severities(db: Session, value: float, kind: str) -> list[str]:
    return [v.severity for v in evaluate(db, "9414290", "water_level", TS, value) if v.kind == kind]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.9, []),  # below every threshold
        (1.1, ["minor"]),  # exactly at minor — thresholds are inclusive
        (1.2, ["minor"]),
        (1.3, ["moderate"]),
        (1.6, ["major"]),
    ],
)
def test_flood_check_maps_levels_to_severity(
    db: Session, value: float, expected: list[str]
) -> None:
    assert _severities(db, value, "flood") == expected


def test_only_water_level_is_evaluated(db: Session) -> None:
    """A prediction is not an observation; it must not raise a flood anomaly."""
    assert evaluate(db, "9414290", "predictions", TS, 9.9) == []


def test_unknown_station_yields_no_verdict(db: Session) -> None:
    """No thresholds means no judgement — and, importantly, no exception.

    Raising here would leave the message unacknowledged and redelivered forever.
    """
    assert evaluate(db, "nope", "water_level", TS, 99.0) == []


def test_handle_message_records_a_crossing(db: Session) -> None:
    handle_message(db, _event(1.4))

    rows = db.scalars(select(Anomaly)).all()
    assert len(rows) == 1
    assert rows[0].kind == "flood"
    assert rows[0].severity == "moderate"
    assert rows[0].value == 1.4
    assert rows[0].station_id == "9414290"


def test_handle_message_records_nothing_when_clear(db: Session) -> None:
    handle_message(db, _event(0.5))

    assert db.scalars(select(Anomaly)).all() == []


# --- surge: the level relative to what the tide tables predicted ---


def _predict(db: Session, value: float, ts: datetime = TS) -> None:
    db.add(Reading(station_id="9414290", product="predictions", ts=ts, value=value))
    db.commit()


def test_no_surge_when_the_observation_matches_the_prediction(db: Session) -> None:
    _predict(db, 0.50)

    assert _severities(db, 0.55, "surge") == []  # 0.05 m, inside the 0.15 threshold


def test_surge_above_prediction_is_flagged(db: Session) -> None:
    _predict(db, 0.50)

    verdicts = [v for v in evaluate(db, "9414290", "water_level", TS, 0.90) if v.kind == "surge"]
    assert len(verdicts) == 1
    assert verdicts[0].severity == "above"
    assert verdicts[0].residual == 0.4


def test_surge_below_prediction_is_flagged(db: Session) -> None:
    """Water lower than predicted matters too — offshore wind, not just storms."""
    _predict(db, 0.90)

    verdicts = [v for v in evaluate(db, "9414290", "water_level", TS, 0.50) if v.kind == "surge"]
    assert len(verdicts) == 1
    assert verdicts[0].severity == "below"
    assert verdicts[0].residual == -0.4


def test_no_surge_verdict_without_a_prediction(db: Session) -> None:
    """A missing prediction is absence of evidence, not evidence of calm."""
    assert _severities(db, 5.0, "surge") == []


def test_a_reading_can_be_both_flooding_and_surging(db: Session) -> None:
    """The two checks answer different questions, so both can fire at once."""
    _predict(db, 0.50)  # predicted low tide, observed well above a flood threshold

    handle_message(db, _event(1.4))

    rows = db.scalars(select(Anomaly).order_by(Anomaly.kind)).all()
    assert [r.kind for r in rows] == ["flood", "surge"]
    assert rows[0].severity == "moderate"
    assert rows[1].residual == 0.9


def test_surge_catches_what_an_absolute_threshold_misses(db: Session) -> None:
    """The point of the residual: 0.9 m is under every flood threshold here, but
    it is 0.4 m above what the tide tables said, which is the storm signature."""
    _predict(db, 0.50)

    kinds = {v.kind for v in evaluate(db, "9414290", "water_level", TS, 0.90)}
    assert kinds == {"surge"}
