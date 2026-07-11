"""Thin client for the NOAA CO-OPS data API.

API reference: https://api.tidesandcurrents.noaa.gov/api/prod/
All requests use GMT and metric units; timestamps are returned as naive UTC.

The client is resilient to NOAA's occasional flakiness: transient failures
(network errors and 5xx responses) are retried with exponential backoff, and
identical requests are memoized for a short TTL so a single operation never
hammers the same series twice. Deterministic failures — a 4xx, an error
payload, or a non-JSON body — are surfaced immediately without retrying, since
retrying them would only add latency.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .config import Settings

logger = logging.getLogger("tideline.noaa")

REQUEST_DATE_FMT = "%Y%m%d %H:%M"
RESPONSE_TS_FMT = "%Y-%m-%d %H:%M"

# A (naive UTC timestamp, value) time series.
Series = list[tuple[datetime, float]]


class NoaaError(Exception):
    """The NOAA API was unreachable or returned an error payload."""


# NOAA reports "no sensor for this product here" as an error payload, but for
# our purposes it's a valid, empty answer — not an upstream failure.
NO_DATA_MARKER = "No data was found"


class NoaaClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 15.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        cache_ttl: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.cache_ttl = cache_ttl
        self._sleep = sleep
        # Per-instance memo of recent series, keyed by request identity. Guards
        # against redundant NOAA calls within one operation; the durable cache
        # is the database read-through layer in service.py.
        self._cache: dict[tuple[str, str, datetime, datetime], tuple[float, Series]] = {}

    def fetch_series(self, station_id: str, product: str, begin: datetime, end: datetime) -> Series:
        """Fetch a time series as (naive UTC timestamp, value) pairs."""
        key = (station_id, product, begin, end)
        cached = self._cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < self.cache_ttl:
            logger.debug("noaa cache hit station=%s product=%s", station_id, product)
            return cached[1]
        series = self._fetch_with_retry(station_id, product, begin, end)
        self._cache[key] = (time.monotonic(), series)
        return series

    def _fetch_with_retry(
        self, station_id: str, product: str, begin: datetime, end: datetime
    ) -> Series:
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return self._fetch_once(station_id, product, begin, end)
            except _TransientNoaaError as exc:
                if attempt == attempts:
                    logger.error(
                        "noaa request failed station=%s product=%s attempts=%d error=%s",
                        station_id,
                        product,
                        attempt,
                        exc,
                    )
                    raise NoaaError(str(exc)) from exc
                wait = self.backoff_base * 2 ** (attempt - 1)
                logger.warning(
                    "noaa transient failure station=%s product=%s attempt=%d/%d "
                    "retry_in=%.2fs error=%s",
                    station_id,
                    product,
                    attempt,
                    attempts,
                    wait,
                    exc,
                )
                self._sleep(wait)
        raise AssertionError("unreachable")  # pragma: no cover

    def _fetch_once(self, station_id: str, product: str, begin: datetime, end: datetime) -> Series:
        params = {
            "station": station_id,
            "product": product,
            "begin_date": begin.strftime(REQUEST_DATE_FMT),
            "end_date": end.strftime(REQUEST_DATE_FMT),
            "datum": "MLLW",
            "units": "metric",
            "time_zone": "gmt",
            "format": "json",
            "application": "tideline",
        }
        try:
            resp = httpx.get(self.base_url, params=params, timeout=self.timeout)
        except httpx.HTTPError as exc:
            # Connect/read timeouts and other transport errors are worth retrying.
            raise _TransientNoaaError(f"NOAA request failed: {exc}") from exc

        if resp.status_code >= 500:
            raise _TransientNoaaError(f"NOAA returned HTTP {resp.status_code}")
        if resp.status_code >= 400:
            # A 4xx won't fix itself on retry — surface it immediately.
            raise NoaaError(f"NOAA returned HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except ValueError as exc:
            # A 200 with a non-JSON body (e.g. an HTML maintenance page) is
            # ambiguous but deterministic for this response — fail without retry.
            raise NoaaError(f"NOAA request failed: {exc}") from exc

        if "error" in payload:
            message = payload["error"].get("message", "unknown NOAA error").strip()
            if NO_DATA_MARKER in message:
                return []
            raise NoaaError(message)

        # Observed products return rows under "data", predictions under "predictions"
        rows = payload.get("data") or payload.get("predictions") or []
        series: Series = []
        for row in rows:
            if not row.get("v"):  # sensor gaps come back as empty strings
                continue
            ts = datetime.strptime(row["t"], RESPONSE_TS_FMT)
            series.append((ts, float(row["v"])))
        return series


class _TransientNoaaError(Exception):
    """A NOAA failure worth retrying (network error or 5xx)."""


def make_noaa_client(settings: "Settings") -> NoaaClient:
    """Build a NoaaClient wired up from application settings."""
    return NoaaClient(
        settings.noaa_base_url,
        max_retries=settings.noaa_max_retries,
        backoff_base=settings.noaa_backoff_base,
        cache_ttl=settings.noaa_cache_ttl_seconds,
    )
