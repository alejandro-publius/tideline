"""Read-through cache between the REST API and NOAA.

Every refresh persists readings to the database, so history accumulates
across pulls. Freshness is tracked per (station, product) in a fetch log.
Refreshes always pull the full supported window (not just the requested
range) so a narrow request can't mark a wide range as fresh. When NOAA is
unreachable, previously cached data is served with source="stale".
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from . import metrics
from .config import get_settings
from .models import FetchLog, Reading, Station
from .noaa import NoaaClient, NoaaError

logger = logging.getLogger("tideline.service")

Source = Literal["noaa", "cache", "stale"]

# Widest range the API serves; refreshes always cover it in full.
MAX_LOOKBACK_HOURS = 72
PREDICTIONS_LOOKAHEAD_HOURS = 48

# Failure cooldown: when NOAA fails for a (station, product) pair, remember it
# so the next requests within the window serve stale immediately instead of
# each re-paying the full retry/timeout cost — an outage must be absorbed, not
# amplified. Keyed on monotonic time; bounded at stations x products entries.
_last_failure: dict[tuple[str, str], float] = {}


class UpstreamUnavailable(Exception):
    """NOAA failed and there is no cached data to fall back on."""


@dataclass
class SeriesResult:
    source: Source  # "noaa" (fresh pull) | "cache" (within TTL) | "stale" (NOAA down)
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
        # Over-fetch by the TTL: a fetch is considered fresh for the whole TTL
        # window, so it must cover the full look-ahead as seen from the *end*
        # of that window — otherwise a request near the TTL's edge would get a
        # "fresh" response whose future coverage has silently eroded.
        return begin, now + timedelta(hours=PREDICTIONS_LOOKAHEAD_HOURS) + _ttl_for(product)
    return begin, now


def _needs_refresh(log: FetchLog | None, product: str, now: datetime) -> bool:
    return log is None or now - log.fetched_at >= _ttl_for(product)


def _in_failure_cooldown(station_id: str, product: str) -> bool:
    cooldown = get_settings().noaa_failure_cooldown_seconds
    if cooldown <= 0:
        return False
    last = _last_failure.get((station_id, product))
    return last is not None and time.monotonic() - last < cooldown


def _record_failure(station_id: str, product: str) -> None:
    _last_failure[(station_id, product)] = time.monotonic()


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
    source: Source = "cache"

    if _needs_refresh(log, product, now):
        if _in_failure_cooldown(station.id, product):
            # NOAA just failed for this pair; don't re-pay the retry cost on
            # every request — serve stale until the cooldown expires.
            if log is None:
                raise UpstreamUnavailable("NOAA unavailable (failure cooldown)")
            source = "stale"
        else:
            try:
                fetch_begin, fetch_end = _fetch_window(product, now)
                series = client.fetch_series(station.id, product, fetch_begin, fetch_end)
            except NoaaError as exc:
                _record_failure(station.id, product)
                if log is None:
                    raise UpstreamUnavailable(str(exc)) from exc
                logger.warning(
                    "serving stale data after NOAA failure",
                    extra={"station": station.id, "product": product},
                )
                source = "stale"
            else:
                _store(db, station.id, product, series)
                log = _touch_log(db, log, station.id, product, now)
                source = "noaa"

    metrics.CACHE_LOOKUPS.inc(result=source)
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

    def insert_missing() -> None:
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

    try:
        insert_missing()
    except IntegrityError:
        # Two sessions (a request and the background sweep, or two concurrent
        # requests) can both find the same pair stale and race this upsert; the
        # loser trips the unique constraint. Re-read what the winner committed
        # and insert only the still-missing rows — one retry suffices, since
        # identical refreshes can't conflict twice.
        db.rollback()
        insert_missing()


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
        if _needs_refresh(db.get(FetchLog, (station.id, product)), product, now)
        and not _in_failure_cooldown(station.id, product)
    ]
    if not stale:
        return

    def fetch(pair: tuple[Station, str]):
        station, product = pair
        begin, end = _fetch_window(product, now)
        try:
            return station, product, client.fetch_series(station.id, product, begin, end)
        except NoaaError:
            _record_failure(station.id, product)
            return station, product, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(fetch, stale))

    for station, product, series in results:
        if series is None:
            continue
        _store(db, station.id, product, series)
        _touch_log(db, db.get(FetchLog, (station.id, product)), station.id, product, now)


def overview_from_db(db: Session) -> list[StationOverview]:
    """Latest observed/predicted/surge per station, read straight from the DB.

    The read-only half of get_overview: no NOAA calls, so it reflects whatever
    the cache and background sweep have already collected. Shared by the HTTP
    overview endpoint (after a refresh) and the MCP server (which only reads).
    """
    stations = list(db.scalars(select(Station).order_by(Station.name)))
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


def get_overview(db: Session, client: NoaaClient) -> list[StationOverview]:
    """Latest observed level, prediction, and surge for every station.

    Refreshes any stale series from NOAA, then reads the result back.
    """
    stations = list(db.scalars(select(Station).order_by(Station.name)))
    _refresh_stale_series(db, client, stations, OVERVIEW_PRODUCTS)
    return overview_from_db(db)


@dataclass
class DailySurge:
    """One UTC day of surge-residual statistics from accumulated history."""

    day: date
    avg_surge: float
    max_surge: float
    samples: int


def daily_surge(db: Session, station_id: str, days: int) -> list[DailySurge]:
    """Per-day surge statistics for a station over the trailing `days` window.

    Pairs each observation with the prediction at the same timestamp and
    aggregates the difference per UTC day. Reads only the database — no NOAA
    calls — so it's shared by the HTTP history endpoint and the MCP server.
    """
    observed, predicted = aliased(Reading), aliased(Reading)
    day = func.date(observed.ts)
    surge = observed.value - predicted.value
    rows = db.execute(
        select(
            day.label("day"),
            func.avg(surge).label("avg_surge"),
            func.max(surge).label("max_surge"),
            func.count().label("samples"),
        )
        .select_from(observed)
        .join(
            predicted,
            (predicted.station_id == observed.station_id)
            & (predicted.ts == observed.ts)
            & (predicted.product == "predictions"),
        )
        .where(
            observed.station_id == station_id,
            observed.product == "water_level",
            observed.ts >= utcnow() - timedelta(days=days),
        )
        .group_by(day)
        .order_by(day)
    ).all()

    # func.date() yields a str on SQLite but a date on Postgres — normalize so
    # callers always get a real date regardless of backend.
    def as_date(value: date | str) -> date:
        return value if isinstance(value, date) else date.fromisoformat(value)

    return [
        DailySurge(
            day=as_date(row.day),
            avg_surge=round(row.avg_surge, 3),
            max_surge=round(row.max_surge, 3),
            samples=row.samples,
        )
        for row in rows
    ]


def _touch_log(
    db: Session, log: FetchLog | None, station_id: str, product: str, now: datetime
) -> FetchLog:
    if log is None:
        log = FetchLog(station_id=station_id, product=product, fetched_at=now)
        db.add(log)
    else:
        log.fetched_at = now
    try:
        db.commit()
    except IntegrityError:
        # Lost an insert race on the (station, product) primary key: another
        # session created the log between our lookup and this commit. Update
        # the winner's row instead.
        db.rollback()
        log = db.get(FetchLog, (station_id, product))
        assert log is not None  # the loser only exists because a winner committed
        log.fetched_at = now
        db.commit()
    return log
