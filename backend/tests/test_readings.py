from datetime import datetime, timedelta

import httpx
import respx
from httpx import Response

from app import service
from app.models import FetchLog, Reading
from tests.conftest import NOAA_URL, water_level_payload

READINGS_URL = "/api/stations/9414290/readings"


def _age_fetch_log(db, minutes: int, product: str = "water_level") -> None:
    log = db.get(FetchLog, ("9414290", product))
    log.fetched_at -= timedelta(minutes=minutes)
    db.commit()


@respx.mock
def test_cold_cache_fetches_from_noaa_and_persists(client, db):
    route = respx.get(NOAA_URL).mock(return_value=Response(200, json=water_level_payload()))

    resp = client.get(READINGS_URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "noaa"
    assert len(body["readings"]) == 10
    assert route.call_count == 1
    # timestamps are serialized as explicit UTC
    assert body["readings"][-1]["ts"].endswith("Z")
    # readings were persisted as history
    assert db.query(Reading).filter_by(station_id="9414290", product="water_level").count() == 10


@respx.mock
def test_warm_cache_serves_from_db_without_calling_noaa(client):
    route = respx.get(NOAA_URL).mock(return_value=Response(200, json=water_level_payload()))

    client.get(READINGS_URL)
    resp = client.get(READINGS_URL)

    assert resp.json()["source"] == "cache"
    assert len(resp.json()["readings"]) == 10
    assert route.call_count == 1


@respx.mock
def test_expired_ttl_triggers_refetch_without_duplicating_rows(client, db):
    route = respx.get(NOAA_URL).mock(return_value=Response(200, json=water_level_payload()))

    client.get(READINGS_URL)
    _age_fetch_log(db, minutes=60)  # past the 10-minute TTL
    resp = client.get(READINGS_URL)

    assert resp.json()["source"] == "noaa"
    assert route.call_count == 2
    # same timestamps re-fetched; the upsert must not duplicate them
    assert db.query(Reading).filter_by(station_id="9414290", product="water_level").count() == 10


@respx.mock
def test_refresh_always_pulls_full_window(client):
    """A narrow request must not mark a wide range as fresh (fetches 72h)."""
    route = respx.get(NOAA_URL).mock(return_value=Response(200, json=water_level_payload()))

    client.get(READINGS_URL + "?hours=2")

    params = route.calls.last.request.url.params
    begin = datetime.strptime(params["begin_date"], "%Y%m%d %H:%M")
    end = datetime.strptime(params["end_date"], "%Y%m%d %H:%M")
    assert end - begin == timedelta(hours=72)


@respx.mock
def test_stale_cache_served_when_noaa_is_down(client, db):
    route = respx.get(NOAA_URL)
    route.side_effect = [Response(200, json=water_level_payload()), Response(500)]

    client.get(READINGS_URL)
    _age_fetch_log(db, minutes=60)
    resp = client.get(READINGS_URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "stale"
    assert len(body["readings"]) == 10
    assert route.call_count == 2


@respx.mock
def test_failure_cooldown_serves_stale_without_repaying_retries(client, db):
    """After a NOAA failure, requests inside the cooldown skip NOAA entirely —
    an outage must be absorbed by the cache, not amplified by every visitor."""
    route = respx.get(NOAA_URL)
    route.side_effect = [Response(200, json=water_level_payload()), Response(500)]

    client.get(READINGS_URL)
    _age_fetch_log(db, minutes=60)
    first = client.get(READINGS_URL)  # trips the failure, starts the cooldown
    second = client.get(READINGS_URL)  # inside the cooldown: no NOAA call

    assert first.json()["source"] == "stale"
    assert second.json()["source"] == "stale"
    assert route.call_count == 2, "the cooldown must absorb the second request"


@respx.mock
def test_failure_cooldown_expires_and_noaa_is_retried(client, db):
    route = respx.get(NOAA_URL)
    route.side_effect = [
        Response(200, json=water_level_payload()),
        Response(500),
        Response(200, json=water_level_payload()),
    ]

    client.get(READINGS_URL)
    _age_fetch_log(db, minutes=60)
    client.get(READINGS_URL)  # fails, cooldown starts
    service._last_failure[("9414290", "water_level")] -= 120  # cooldown elapses

    resp = client.get(READINGS_URL)

    assert resp.json()["source"] == "noaa"
    assert route.call_count == 3


@respx.mock
def test_502_when_noaa_down_and_nothing_cached(client):
    respx.get(NOAA_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    resp = client.get(READINGS_URL)

    assert resp.status_code == 502


@respx.mock
def test_station_without_sensor_returns_empty_series_and_caches_it(client):
    """A missing sensor must be a 200 with no readings, and must not re-poll NOAA."""
    payload = {"error": {"message": "No data was found. Product not offered at this station."}}
    route = respx.get(NOAA_URL).mock(return_value=Response(200, json=payload))

    first = client.get(READINGS_URL + "?product=water_temperature")
    second = client.get(READINGS_URL + "?product=water_temperature")

    assert first.status_code == 200
    assert first.json()["readings"] == []
    assert second.json()["source"] == "cache"
    assert route.call_count == 1, "empty answers must be cached, not retried per request"


def test_unknown_station_returns_404(client):
    resp = client.get("/api/stations/0000000/readings")

    assert resp.status_code == 404


def test_query_validation(client):
    assert client.get(READINGS_URL + "?hours=0").status_code == 422
    assert client.get(READINGS_URL + "?hours=100").status_code == 422
    assert client.get(READINGS_URL + "?product=wind_speed").status_code == 422
