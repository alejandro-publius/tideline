"""Thin client for the NOAA CO-OPS data API.

API reference: https://api.tidesandcurrents.noaa.gov/api/prod/
All requests use GMT and metric units; timestamps are returned as naive UTC.
"""

from datetime import datetime

import httpx

REQUEST_DATE_FMT = "%Y%m%d %H:%M"
RESPONSE_TS_FMT = "%Y-%m-%d %H:%M"


class NoaaError(Exception):
    """The NOAA API was unreachable or returned an error payload."""


# NOAA reports "no sensor for this product here" as an error payload, but for
# our purposes it's a valid, empty answer — not an upstream failure.
NO_DATA_MARKER = "No data was found"


class NoaaClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def fetch_series(
        self, station_id: str, product: str, begin: datetime, end: datetime
    ) -> list[tuple[datetime, float]]:
        """Fetch a time series as (naive UTC timestamp, value) pairs."""
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
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as exc:
            raise NoaaError(f"NOAA request failed: {exc}") from exc

        if "error" in payload:
            message = payload["error"].get("message", "unknown NOAA error").strip()
            if NO_DATA_MARKER in message:
                return []
            raise NoaaError(message)

        # Observed products return rows under "data", predictions under "predictions"
        rows = payload.get("data") or payload.get("predictions") or []
        series: list[tuple[datetime, float]] = []
        for row in rows:
            if not row.get("v"):  # sensor gaps come back as empty strings
                continue
            ts = datetime.strptime(row["t"], RESPONSE_TS_FMT)
            series.append((ts, float(row["v"])))
        return series
