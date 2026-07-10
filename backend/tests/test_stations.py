from app.seed import SEED_STATIONS


def test_list_stations_returns_seeded_stations(client):
    resp = client.get("/api/stations")

    assert resp.status_code == 200
    stations = resp.json()
    assert len(stations) == len(SEED_STATIONS)
    names = [s["name"] for s in stations]
    assert names == sorted(names)
    sf = next(s for s in stations if s["id"] == "9414290")
    assert sf == {
        "id": "9414290",
        "name": "San Francisco",
        "state": "CA",
        "lat": 37.806305,
        "lon": -122.46589,
    }


def test_healthz(client):
    resp = client.get("/api/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
