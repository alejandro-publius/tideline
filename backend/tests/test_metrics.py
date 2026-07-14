import respx
from httpx import Response

from app import metrics
from tests.conftest import NOAA_URL, predictions_payload, water_level_payload


def test_counter_render_includes_help_type_and_labels():
    metrics.HTTP_REQUESTS.inc(method="GET", path="/api/stations", status=200)
    metrics.HTTP_REQUESTS.inc(method="GET", path="/api/stations", status=200)
    metrics.NOAA_RETRIES.inc()

    text = metrics.render()

    assert "# HELP tideline_http_requests_total" in text
    assert "# TYPE tideline_http_requests_total counter" in text
    assert 'tideline_http_requests_total{method="GET",path="/api/stations",status="200"} 2' in text
    assert "tideline_noaa_retries_total 1" in text


def test_unlabeled_counters_render_zero_when_untouched():
    assert "tideline_rate_limited_total 0" in metrics.render()


@respx.mock
def test_requests_are_counted_by_route_template(client):
    """Labels use the route template, not the raw path — station ids and query
    strings must not mint unbounded label values."""
    respx.get(NOAA_URL).mock(
        side_effect=[
            Response(200, json=water_level_payload()),
            Response(200, json=predictions_payload()),
        ]
    )
    client.get("/api/stations/9414290/readings?hours=12")
    client.get("/api/stations/9414290/predictions?hours=12")

    resp = client.get("/api/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert (
        'tideline_http_requests_total{method="GET",'
        'path="/api/stations/{station_id}/readings",status="200"} 1' in body
    )
    assert "9414290" not in body  # no raw ids leaking into labels
    # both endpoints were cold-cache: two fresh NOAA pulls
    assert 'tideline_cache_lookups_total{result="noaa"} 2' in body
    assert 'tideline_noaa_requests_total{outcome="ok"} 2' in body


def test_unmatched_api_paths_collapse_into_one_label(client):
    client.get("/api/nope-1")
    client.get("/api/nope-2")

    body = client.get("/api/metrics").text

    assert 'path="(unmatched)",status="404"} 2' in body
    assert "nope-1" not in body


@respx.mock
def test_noaa_failures_count_as_errors(client):
    respx.get(NOAA_URL).mock(return_value=Response(400))

    assert client.get("/api/stations/9414290/readings").status_code == 502

    body = client.get("/api/metrics").text
    assert 'tideline_noaa_requests_total{outcome="error"} 1' in body
