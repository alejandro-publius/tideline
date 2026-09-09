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
def test_overview_reports_nws_flood_stages(client):
    """One elevated level classifies differently per station's NWS thresholds."""
    # every station "observes" ~2.24 m: above SF minor (2.146), above Virginia
    # Key major (1.442), below Seattle minor (4.103)
    route = respx.get(NOAA_URL).mock(
        side_effect=_responder(water_level_payload(base=2.15), predictions_payload())
    )

    resp = client.get("/api/overview")

    assert resp.status_code == 200
    assert route.call_count == EXPECTED_CALLS
    stages = {row["station"]["id"]: row["flood_stage"] for row in resp.json()["stations"]}
    assert stages["9414290"] == "minor"
    assert stages["8723214"] == "major"
    assert stages["9447130"] is None


@respx.mock
def test_overview_reports_null_surge_when_predictions_are_missing(client):
    """A station with an observed reading but no tide prediction (NOAA's own
    "No data was found" answer, not a failure) must report observed with a
    null predicted/surge -- not crash, and not silently pretend surge is 0."""
    no_predictions = {"error": {"message": "No data was found for this station"}}

    def respond(request):
        if request.url.params["product"] == "predictions":
            return Response(200, json=no_predictions)
        return Response(200, json=water_level_payload())

    route = respx.get(NOAA_URL).mock(side_effect=respond)

    resp = client.get("/api/overview")

    assert resp.status_code == 200
    rows = {row["station"]["id"]: row for row in resp.json()["stations"]}
    for row in rows.values():
        assert row["observed"] == pytest.approx(1.09)
        assert row["predicted"] is None
        assert row["surge"] is None
    assert route.call_count == EXPECTED_CALLS


@respx.mock
def test_overview_survives_a_failing_station(client):
    route = respx.get(NOAA_URL).mock(
        side_effect=_responder(
            water_level_payload(), predictions_payload(), failing_station="9414290"
        )
    )

    resp = client.get("/api/overview")

    assert resp.status_code == 200
    rows = {row["station"]["id"]: row for row in resp.json()["stations"]}
    assert rows["9414290"]["surge"] is None, "failing station reports null, not an error"
    healthy = [r for sid, r in rows.items() if sid != "9414290"]
    assert all(r["surge"] is not None for r in healthy)
    assert route.call_count == EXPECTED_CALLS


@respx.mock
def test_overview_survives_a_duplicate_timestamp_in_one_payload(client):
    """NOAA has, on occasion, repeated a timestamp within a single response
    (e.g. a preliminary reading followed by its verified replacement, both
    still in the same window). One station's payload carrying a duplicate
    timestamp must not corrupt the whole sweep -- every other station's
    surge must still come back, not just the offending one's."""
    dup_payload = water_level_payload()
    dup_row = dict(dup_payload["data"][-1])
    dup_row["v"] = f"{float(dup_row['v']) + 0.01:.3f}"  # revised value, same "t"
    dup_payload["data"].append(dup_row)

    def respond(request):
        if request.url.params["product"] == "predictions":
            return Response(200, json=predictions_payload())
        if request.url.params["station"] == "9414290":
            return Response(200, json=dup_payload)
        return Response(200, json=water_level_payload())

    route = respx.get(NOAA_URL).mock(side_effect=respond)

    resp = client.get("/api/overview")

    assert resp.status_code == 200
    rows = {row["station"]["id"]: row for row in resp.json()["stations"]}
    assert len(rows) == len(SEED_STATIONS)
    # the one station with the duplicated timestamp still resolves to a value
    assert rows["9414290"]["surge"] is not None
    # crucially, every OTHER station must not be dragged down by that one bad payload
    healthy = [r for sid, r in rows.items() if sid != "9414290"]
    assert all(r["surge"] is not None for r in healthy)
    assert route.call_count == EXPECTED_CALLS
