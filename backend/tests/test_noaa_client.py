from datetime import datetime

import pytest
import respx
from httpx import Response

from app.noaa import NoaaClient, NoaaError
from tests.conftest import NOAA_URL

BEGIN = datetime(2026, 7, 9, 0, 0)
END = datetime(2026, 7, 9, 12, 0)


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
