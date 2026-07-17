from datetime import datetime, timedelta

import respx
from httpx import Response

from app.service import utcnow
from tests.conftest import NOAA_URL, predictions_payload


@respx.mock
def test_predictions_window_extends_into_the_future(client):
    route = respx.get(NOAA_URL).mock(
        return_value=Response(200, json=predictions_payload(hours_back=2, hours_ahead=2))
    )

    resp = client.get("/api/stations/9414290/predictions?hours=3")

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "noaa"
    assert body["product"] == "predictions"
    assert route.call_count == 1
    last_ts = datetime.fromisoformat(body["readings"][-1]["ts"].removesuffix("Z"))
    assert last_ts > utcnow(), "predictions should include future tide levels"


@respx.mock
def test_predictions_accept_72h_lookback_but_cap_lookahead_at_48h(client):
    route = respx.get(NOAA_URL).mock(return_value=Response(200, json=predictions_payload()))

    resp = client.get("/api/stations/9414290/predictions?hours=72")

    assert resp.status_code == 200
    assert route.call_count == 1
    assert client.get("/api/stations/9414290/predictions?hours=73").status_code == 422


@respx.mock
def test_predictions_fetch_covers_lookahead_through_the_whole_ttl(client):
    """The fetched window must cover the full 48 h look-ahead even for a
    request at the TTL's edge — over-fetch by the TTL so a "fresh" cache can
    never be missing part of the promised future window."""
    route = respx.get(NOAA_URL).mock(return_value=Response(200, json=predictions_payload()))

    client.get("/api/stations/9414290/predictions")

    params = route.calls.last.request.url.params
    begin = datetime.strptime(params["begin_date"], "%Y%m%d %H:%M")
    end = datetime.strptime(params["end_date"], "%Y%m%d %H:%M")
    # 72 h lookback + 48 h lookahead + 12 h TTL over-fetch
    assert end - begin == timedelta(hours=72 + 48 + 12)


@respx.mock
def test_series_responses_are_gzipped(client):
    respx.get(NOAA_URL).mock(return_value=Response(200, json=predictions_payload(48, 48)))

    resp = client.get(
        "/api/stations/9414290/predictions?hours=48", headers={"accept-encoding": "gzip"}
    )

    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
