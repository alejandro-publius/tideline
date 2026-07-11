"""End-to-end: seed synthetic data, then exercise the app with NOAA offline.

This is the path a reviewer takes — `python -m app.seed_demo` and browse — so
the test asserts the whole read surface works from the database alone and that
NOAA is never contacted.
"""

import respx
from httpx import Response

from app.seed_demo import seed_demo
from tests.conftest import NOAA_URL


@respx.mock
def test_seeded_demo_serves_every_endpoint_without_touching_noaa(client, db):
    # Any NOAA call would 500; we assert it never happens.
    route = respx.get(NOAA_URL).mock(return_value=Response(500))

    written = seed_demo(db, days=3)
    assert written > 0

    overview = client.get("/api/overview")
    assert overview.status_code == 200
    stations = overview.json()["stations"]
    assert len(stations) == 13
    assert all(s["observed"] is not None for s in stations), "every station has recent data"
    assert any(s["surge"] is not None for s in stations)

    history = client.get("/api/stations/9414290/history?days=7").json()
    assert len(history) >= 3, "several days of surge aggregates"
    assert all(row["samples"] > 0 for row in history)

    csv_rows = client.get("/api/stations/9414290/export?days=7").text.strip().splitlines()
    assert csv_rows[0] == "ts,observed_m,predicted_m,surge_m"
    assert len(csv_rows) > 100, "a dense 6-minute series, not a handful of points"

    readings = client.get("/api/stations/9414290/readings?hours=24").json()
    assert readings["source"] == "cache", "freshly seeded fetch-log means no refetch"
    assert readings["readings"]

    assert route.call_count == 0, "seeded data must serve entirely offline"
