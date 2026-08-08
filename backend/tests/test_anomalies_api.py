"""API tests for the anomalies endpoint (ADR 0007)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Anomaly


@pytest.fixture
def seeded(db: Session) -> Session:
    """Stations come from conftest's seed; this adds the anomalies to read back."""
    db.add_all(
        [
            Anomaly(
                station_id="9414290",
                product="water_level",
                ts=datetime(2026, 8, 8, 10, 0),
                value=1.4,
                kind="flood",
                severity="moderate",
                residual=None,
                detected_at=datetime(2026, 8, 8, 10, 1),
            ),
            Anomaly(
                station_id="9414290",
                product="water_level",
                ts=datetime(2026, 8, 8, 12, 0),
                value=0.9,
                kind="surge",
                severity="above",
                residual=0.4,
                detected_at=datetime(2026, 8, 8, 12, 1),
            ),
        ]
    )
    db.commit()
    return db


def test_anomalies_are_returned_newest_first(client: TestClient, seeded: Session) -> None:
    body = client.get("/api/anomalies").json()

    assert [a["kind"] for a in body["anomalies"]] == ["surge", "flood"]


def test_anomaly_carries_its_station_name_and_residual(client: TestClient, seeded: Session) -> None:
    surge = client.get("/api/anomalies").json()["anomalies"][0]

    assert surge["station_name"] == "San Francisco"
    assert surge["residual"] == 0.4
    assert surge["severity"] == "above"
    # Storage is naive UTC; the wire format is explicit about it (ADR 0003).
    assert surge["ts"].endswith("Z")


def test_flood_anomalies_have_no_residual(client: TestClient, seeded: Session) -> None:
    flood = client.get("/api/anomalies?kind=flood").json()["anomalies"][0]

    assert flood["residual"] is None


@pytest.mark.parametrize(("kind", "expected"), [("flood", 1), ("surge", 1)])
def test_filtering_by_kind(client: TestClient, seeded: Session, kind: str, expected: int) -> None:
    body = client.get(f"/api/anomalies?kind={kind}").json()

    assert len(body["anomalies"]) == expected
    assert all(a["kind"] == kind for a in body["anomalies"])


def test_unknown_kind_is_rejected(client: TestClient, seeded: Session) -> None:
    assert client.get("/api/anomalies?kind=nonsense").status_code == 422


def test_limit_is_bounded(client: TestClient, seeded: Session) -> None:
    assert client.get("/api/anomalies?limit=0").status_code == 422
    assert client.get("/api/anomalies?limit=9999").status_code == 422


def test_no_anomalies_is_an_empty_list_not_an_error(client: TestClient) -> None:
    """A quiet system and a broken one must not look the same to the caller."""
    response = client.get("/api/anomalies")

    assert response.status_code == 200
    assert response.json() == {"anomalies": []}
