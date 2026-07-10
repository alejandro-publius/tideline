"""Read-through cache between the REST API and NOAA.

Every refresh persists readings to the database, so history accumulates
across pulls. Freshness is tracked per (station, product) in a fetch log.
Refreshes always pull the full supported window (not just the requested
range) so a narrow request can't mark a wide range as fresh. When NOAA is
unreachable, previously cached data is served with source="stale".
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import FetchLog, Reading, Station
from .noaa import NoaaClient, NoaaError

# Widest range the API serves; refreshes always cover it in full.
MAX_LOOKBACK_HOURS = 72
PREDICTIONS_LOOKAHEAD_HOURS = 48


class UpstreamUnavailable(Exception):
    """NOAA failed and there is no cached data to fall back on."""


@dataclass
class SeriesResult:
    source: str  # "noaa" (fresh pull) | "cache" (within TTL) | "stale" (NOAA down)
    fetched_at: datetime | None
    readings: list[Reading]


def utcnow() -> datetime:
    """Naive UTC now; all timestamps in the system are naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ttl_for(product: str) -> timedelta:
    settings = get_settings()
    if product == "predictions":  # astronomical tides don't change minute to minute
        return timedelta(minutes=settings.predictions_ttl_minutes)
    return timedelta(minutes=settings.cache_ttl_minutes)


def _fetch_window(product: str, now: datetime) -> tuple[datetime, datetime]:
    begin = now - timedelta(hours=MAX_LOOKBACK_HOURS)
    if product == "predictions":
        return begin, now + timedelta(hours=PREDICTIONS_LOOKAHEAD_HOURS)
    return begin, now


def get_series(
    db: Session,
    client: NoaaClient,
    station: Station,
    product: str,
    begin: datetime,
    end: datetime,
) -> SeriesResult:
    log = db.get(FetchLog, (station.id, product))
    now = utcnow()
    source = "cache"

    if log is None or now - log.fetched_at >= _ttl_for(product):
        try:
            fetch_begin, fetch_end = _fetch_window(product, now)
            series = client.fetch_series(station.id, product, fetch_begin, fetch_end)
        except NoaaError as exc:
            if log is None:
                raise UpstreamUnavailable(str(exc)) from exc
            source = "stale"
        else:
            _store(db, station.id, product, series)
            log = _touch_log(db, log, station.id, product, now)
            source = "noaa"

    readings = db.scalars(
        select(Reading)
        .where(
            Reading.station_id == station.id,
            Reading.product == product,
            Reading.ts >= begin,
            Reading.ts <= end,
        )
        .order_by(Reading.ts)
    ).all()
    return SeriesResult(
        source=source,
        fetched_at=log.fetched_at if log else None,
        readings=list(readings),
    )


def _store(
    db: Session, station_id: str, product: str, series: list[tuple[datetime, float]]
) -> None:
    """Insert new rows, skipping timestamps already recorded (portable upsert)."""
    if not series:
        return
    existing = set(
        db.scalars(
            select(Reading.ts).where(
                Reading.station_id == station_id,
                Reading.product == product,
                Reading.ts.in_([ts for ts, _ in series]),
            )
        )
    )
    db.add_all(
        Reading(station_id=station_id, product=product, ts=ts, value=value)
        for ts, value in series
        if ts not in existing
    )
    db.commit()


OVERVIEW_PRODUCTS = ("water_level", "predictions")


@dataclass
class StationOverview:
    station: Station
    ts: datetime | None
    observed: float | None
    predicted: float | None
    surge: float | None
    flood_stage: str | None = None


def flood_stage(level: float | None, station: Station) -> str | None:
    """NWS flood stage for a water level, worst applicable stage first."""
    if level is None:
        return None
    for stage, threshold in (
        ("major", station.flood_major),
        ("moderate", station.flood_moderate),
        ("minor", station.flood_minor),
    ):
        if threshold is not None and level >= threshold:
            return stage
    return None


def _refresh_stale_series(
    db: Session,
    client: NoaaClient,
    stations: list[Station],
    products: tuple[str, ...],
    max_workers: int = 6,
) -> None:
    """Bring every (station, product) up to date in one sweep.

    NOAA requests run in parallel threads (pure I/O, no DB access);
    SQLite writes stay on the calling thread. Stations NOAA fails for
    are simply skipped — an overview must not die on one bad station.
    """
    now = utcnow()
    stale = [
        (station, product)
        for station in stations
        for product in products
        if (log := db.get(FetchLog, (station.id, product))) is None
        or now - log.fetched_at >= _ttl_for(product)
    ]
    if not stale:
        return

    def fetch(pair: tuple[Station, str]):
        station, product = pair
        begin, end = _fetch_window(product, now)
        try:
            return station, product, client.fetch_series(station.id, product, begin, end)
        except NoaaError:
            return station, product, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(fetch, stale))

    for station, product, series in results:
        if series is None:
            continue
        _store(db, station.id, product, series)
        _touch_log(db, db.get(FetchLog, (station.id, product)), station.id, product, now)


def get_overview(db: Session, client: NoaaClient) -> list[StationOverview]:
    """Latest observed level, prediction, and surge for every station."""
    stations = list(db.scalars(select(Station).order_by(Station.name)))
    _refresh_stale_series(db, client, stations, OVERVIEW_PRODUCTS)

    horizon = utcnow() - timedelta(hours=2)
    rows: list[StationOverview] = []
    for station in stations:
        row = StationOverview(station=station, ts=None, observed=None, predicted=None, surge=None)
        observed = db.scalars(
            select(Reading)
            .where(
                Reading.station_id == station.id,
                Reading.product == "water_level",
                Reading.ts >= horizon,
            )
            .order_by(Reading.ts.desc())
            .limit(1)
        ).first()
        if observed is not None:
            row.ts, row.observed = observed.ts, observed.value
            row.flood_stage = flood_stage(observed.value, station)
            predicted = db.scalars(
                select(Reading).where(
                    Reading.station_id == station.id,
                    Reading.product == "predictions",
                    Reading.ts == observed.ts,
                )
            ).first()
            if predicted is not None:
                row.predicted = predicted.value
                row.surge = round(observed.value - predicted.value, 3)
        rows.append(row)
    return rows


def _touch_log(
    db: Session, log: FetchLog | None, station_id: str, product: str, now: datetime
) -> FetchLog:
    if log is None:
        log = FetchLog(station_id=station_id, product=product, fetched_at=now)
        db.add(log)
    else:
        log.fetched_at = now
    db.commit()
    return log
