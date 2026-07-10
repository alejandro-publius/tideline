from datetime import datetime

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
