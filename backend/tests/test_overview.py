import pytest
import respx
from httpx import Response

from app.seed import SEED_STATIONS
from tests.conftest import NOAA_URL, predictions_payload, water_level_payload

# 13 stations x (water_level + predictions)
EXPECTED_CALLS = len(SEED_STATIONS) * 2


def _responder(wl_payload, pred_payload, failing_station=None):
    """Serve the right payload per product; optionally 500 one station."""

    def respond(request):
        if request.url.params["station"] == failing_station:
            return Response(500)
        if request.url.params["product"] == "predictions":
            return Response(200, json=pred_payload)
        return Response(200, json=wl_payload)

    return respond


@respx.mock
def test_overview_computes_surge_for_every_station(client):
    route = respx.get(NOAA_URL).mock(
        side_effect=_responder(water_level_payload(), predictions_payload())
    )

    resp = client.get("/api/overview")

    assert resp.status_code == 200
    rows = resp.json()["stations"]
    assert len(rows) == len(SEED_STATIONS)
    assert route.call_count == EXPECTED_CALLS
    for row in rows:
        # mocked series: latest observed 1.09, prediction at the same instant 1.5
        assert row["observed"] == pytest.approx(1.09)
        assert row["predicted"] == pytest.approx(1.5)
        assert row["surge"] == pytest.approx(-0.41)
        assert row["ts"].endswith("Z")


@respx.mock
def test_overview_is_cached_within_ttl(client):
    route = respx.get(NOAA_URL).mock(
        side_effect=_responder(water_level_payload(), predictions_payload())
    )

    client.get("/api/overview")
    resp = client.get("/api/overview")

    assert resp.status_code == 200
    assert route.call_count == EXPECTED_CALLS, "second overview must be served from the cache"


@respx.mock
def test_overview_survives_a_failing_station(client):
    route = respx.get(NOAA_URL).mock(
        side_effect=_responder(water_level_payload(), predictions_payload(), failing_station="9414290")
    )

    resp = client.get("/api/overview")

    assert resp.status_code == 200
    rows = {row["station"]["id"]: row for row in resp.json()["stations"]}
    assert rows["9414290"]["surge"] is None, "failing station reports null, not an error"
    healthy = [r for sid, r in rows.items() if sid != "9414290"]
    assert all(r["surge"] is not None for r in healthy)
    assert route.call_count == EXPECTED_CALLS