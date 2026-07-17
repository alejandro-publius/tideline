from datetime import datetime

import httpx
import pytest
import respx
from httpx import Response

from app.noaa import NoaaClient, NoaaError
from tests.conftest import NOAA_URL

BEGIN = datetime(2026, 7, 9, 0, 0)
END = datetime(2026, 7, 9, 12, 0)


def _client(**kwargs) -> NoaaClient:
    """A client that never actually sleeps between retries."""
    kwargs.setdefault("sleep", lambda _seconds: None)
    return NoaaClient(NOAA_URL, **kwargs)


@respx.mock
def test_parses_series_and_skips_sensor_gaps():
    payload = {
        "metadata": {"id": "9414290", "name": "San Francisco"},
        "data": [
            {"t": "2026-07-09 10:00", "v": "1.234", "s": "0.05", "f": "0,0,0,0", "q": "p"},
            {"t": "2026-07-09 10:06", "v": "", "s": "", "f": "0,0,0,1", "q": "p"},
            {"t": "2026-07-09 10:12", "v": "1.301", "s": "0.05", "f": "0,0,0,0", "q": "p"},
        ],
    }
    respx.get(NOAA_URL).mock(return_value=Response(200, json=payload))

    series = NoaaClient(NOAA_URL).fetch_series("9414290", "water_level", BEGIN, END)

    assert series == [
        (datetime(2026, 7, 9, 10, 0), 1.234),
        (datetime(2026, 7, 9, 10, 12), 1.301),
    ]


@respx.mock
def test_no_data_error_is_an_empty_series_not_a_failure():
    """'No data was found' means no sensor / empty window — a valid answer."""
    payload = {
        "error": {"message": "No data was found. This product may not be offered at this station."}
    }
    respx.get(NOAA_URL).mock(return_value=Response(200, json=payload))

    series = NoaaClient(NOAA_URL).fetch_series("9414290", "water_temperature", BEGIN, END)

    assert series == []


@respx.mock
def test_non_json_body_raises_noaa_error_not_a_crash():
    """A 200 with an HTML maintenance page must degrade like any NOAA failure."""
    respx.get(NOAA_URL).mock(return_value=Response(200, text="<html>scheduled maintenance</html>"))

    with pytest.raises(NoaaError, match="NOAA request failed"):
        NoaaClient(NOAA_URL).fetch_series("9414290", "water_level", BEGIN, END)


@respx.mock
def test_error_payload_raises_noaa_error():
    payload = {"error": {"message": " The station is not a valid station. "}}
    respx.get(NOAA_URL).mock(return_value=Response(200, json=payload))

    with pytest.raises(NoaaError, match="not a valid station"):
        NoaaClient(NOAA_URL).fetch_series("0000000", "water_level", BEGIN, END)


@respx.mock
def test_sends_expected_query_params():
    respx.get(NOAA_URL).mock(return_value=Response(200, json={"data": []}))

    NoaaClient(NOAA_URL).fetch_series("9414290", "water_level", BEGIN, END)

    params = respx.calls.last.request.url.params
    assert params["station"] == "9414290"
    assert params["product"] == "water_level"
    assert params["datum"] == "MLLW"
    assert params["units"] == "metric"
    assert params["time_zone"] == "gmt"
    assert params["begin_date"] == "20260709 00:00"


@respx.mock
def test_retries_transient_5xx_then_succeeds():
    """A blip (503) is retried; the follow-up 200 is served normally."""
    route = respx.get(NOAA_URL)
    route.side_effect = [
        Response(503),
        Response(200, json={"data": [{"t": "2026-07-09 10:00", "v": "1.5"}]}),
    ]

    series = _client(max_retries=3).fetch_series("9414290", "water_level", BEGIN, END)

    assert series == [(datetime(2026, 7, 9, 10, 0), 1.5)]
    assert route.call_count == 2


@respx.mock
def test_retries_network_errors_then_gives_up():
    """A persistent connection failure exhausts retries and raises NoaaError."""
    route = respx.get(NOAA_URL).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(NoaaError, match="NOAA request failed"):
        _client(max_retries=2).fetch_series("9414290", "water_level", BEGIN, END)

    assert route.call_count == 3  # 1 initial + 2 retries


@respx.mock
def test_backoff_grows_exponentially():
    """Waits follow base * 2**n; no sleep is longer than the one after it."""
    respx.get(NOAA_URL).mock(side_effect=httpx.ConnectError("refused"))
    waits: list[float] = []

    with pytest.raises(NoaaError):
        NoaaClient(NOAA_URL, max_retries=3, backoff_base=0.5, sleep=waits.append).fetch_series(
            "9414290", "water_level", BEGIN, END
        )

    assert waits == [0.5, 1.0, 2.0]


@respx.mock
def test_4xx_is_not_retried():
    """A client error is deterministic — surface it on the first response."""
    route = respx.get(NOAA_URL).mock(return_value=Response(404))

    with pytest.raises(NoaaError, match="HTTP 404"):
        _client(max_retries=3).fetch_series("9414290", "water_level", BEGIN, END)

    assert route.call_count == 1


@respx.mock
def test_error_payload_is_not_retried():
    """A NOAA error payload won't change on retry."""
    route = respx.get(NOAA_URL).mock(
        return_value=Response(200, json={"error": {"message": "not a valid station"}})
    )

    with pytest.raises(NoaaError, match="not a valid station"):
        _client(max_retries=3).fetch_series("0000000", "water_level", BEGIN, END)

    assert route.call_count == 1
