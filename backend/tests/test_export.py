from datetime import timedelta

from app.models import Reading
from app.service import utcnow


def _insert_pair(db, ts, observed: float, predicted: float) -> None:
    db.add(Reading(station_id="9414290", product="water_level", ts=ts, value=observed))
    db.add(Reading(station_id="9414290", product="predictions", ts=ts, value=predicted))


def test_export_streams_joined_history_as_csv(client, db):
    base = utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    _insert_pair(db, base, observed=1.25, predicted=1.0)
    _insert_pair(db, base + timedelta(hours=1), observed=0.9, predicted=1.1)
    # an unpaired observation (no prediction at that ts) is not a dataset row
    db.add(
        Reading(
            station_id="9414290",
            product="water_level",
            ts=base + timedelta(hours=2),
            value=9.9,
        )
    )
    db.commit()

    resp = client.get("/api/stations/9414290/export?days=7")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="tideline_9414290_7d.csv"' in resp.headers["content-disposition"]
    header, *rows = resp.text.strip().split("\n")
    assert header == "ts,observed_m,predicted_m,surge_m"
    assert len(rows) == 2
    assert rows[0] == f"{base.isoformat()}Z,1.25,1.0,0.25"
    assert rows[1].endswith(",0.9,1.1,-0.2")


def test_export_respects_days_window(client, db):
    old = utcnow() - timedelta(days=40)
    _insert_pair(db, old, observed=1.0, predicted=1.0)
    db.commit()

    within = client.get("/api/stations/9414290/export?days=60").text.strip().split("\n")
    outside = client.get("/api/stations/9414290/export?days=30").text.strip().split("\n")

    assert len(within) == 2  # header + the row
    assert len(outside) == 1  # header only


def test_export_validation_and_unknown_station(client):
    assert client.get("/api/stations/9414290/export?days=0").status_code == 422
    assert client.get("/api/stations/9414290/export?days=400").status_code == 422
    assert client.get("/api/stations/0000000/export").status_code == 404
