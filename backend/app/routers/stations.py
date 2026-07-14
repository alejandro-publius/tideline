from collections.abc import Iterator
from datetime import timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from ..config import get_settings
from ..database import get_db
from ..models import Reading, Station
from ..noaa import NoaaClient, make_noaa_client
from ..schemas import DailySurgeOut, ReadingOut, SeriesOut, StationOut
from ..service import PREDICTIONS_LOOKAHEAD_HOURS, UpstreamUnavailable, get_series, utcnow

router = APIRouter(prefix="/api/stations", tags=["stations"])


class ObservedProduct(str, Enum):
    water_level = "water_level"
    water_temperature = "water_temperature"


def get_noaa_client() -> NoaaClient:
    return make_noaa_client(get_settings())


def _get_station(db: Session, station_id: str) -> Station:
    station = db.get(Station, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail=f"Unknown station {station_id!r}")
    return station


@router.get("", response_model=list[StationOut])
def list_stations(db: Session = Depends(get_db)) -> list[Station]:
    return list(db.scalars(select(Station).order_by(Station.name)))


@router.get("/{station_id}/readings", response_model=SeriesOut)
def get_readings(
    station_id: str,
    product: ObservedProduct = ObservedProduct.water_level,
    hours: int = Query(default=24, ge=1, le=72),
    db: Session = Depends(get_db),
    client: NoaaClient = Depends(get_noaa_client),
) -> SeriesOut:
    """Observed readings for the trailing `hours` window."""
    station = _get_station(db, station_id)
    end = utcnow()
    return _series_response(db, client, station, product.value, end - timedelta(hours=hours), end)


@router.get("/{station_id}/predictions", response_model=SeriesOut)
def get_predictions(
    station_id: str,
    hours: int = Query(default=24, ge=1, le=72),
    db: Session = Depends(get_db),
    client: NoaaClient = Depends(get_noaa_client),
) -> SeriesOut:
    """Astronomical tide predictions from `hours` ago to up to 48 h ahead.

    The window extends into the future so the UI can chart the upcoming tide
    alongside what was observed.
    """
    station = _get_station(db, station_id)
    now = utcnow()
    ahead = timedelta(hours=min(hours, PREDICTIONS_LOOKAHEAD_HOURS))
    return _series_response(
        db, client, station, "predictions", now - timedelta(hours=hours), now + ahead
    )


@router.get("/{station_id}/history", response_model=list[DailySurgeOut])
def get_history(
    station_id: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> list[DailySurgeOut]:
    """Daily surge statistics from accumulated history.

    Serves whatever the database has collected (via requests and the
    background sweep) — no NOAA calls. Observations are paired with the
    prediction at the same timestamp, then aggregated per UTC day.
    """
    station = _get_station(db, station_id)
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
            observed.station_id == station.id,
            observed.product == "water_level",
            observed.ts >= utcnow() - timedelta(days=days),
        )
        .group_by(day)
        .order_by(day)
    ).all()
    return [
        DailySurgeOut(
            day=row.day,
            avg_surge=round(row.avg_surge, 3),
            max_surge=round(row.max_surge, 3),
            samples=row.samples,
        )
        for row in rows
    ]


@router.get("/{station_id}/export")
def export_history(
    station_id: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Accumulated observed/predicted/surge history as a CSV download.

    The row-level counterpart to /history: the same observed-to-prediction
    join, but exported as a clean, analysis-ready dataset instead of daily
    aggregates. Served entirely from the database — no NOAA calls.
    """
    station = _get_station(db, station_id)
    observed, predicted = aliased(Reading), aliased(Reading)
    # Materialized before streaming: the request-scoped session closes when the
    # endpoint returns, so rows can't be pulled lazily from the response body.
    # A year of 6-minute readings is ~88k rows — a few MB, fine to hold.
    rows = db.execute(
        select(observed.ts, observed.value, predicted.value)
        .join(
            predicted,
            (predicted.station_id == observed.station_id)
            & (predicted.ts == observed.ts)
            & (predicted.product == "predictions"),
        )
        .where(
            observed.station_id == station.id,
            observed.product == "water_level",
            observed.ts >= utcnow() - timedelta(days=days),
        )
        .order_by(observed.ts)
    ).all()

    def csv_lines() -> Iterator[str]:
        yield "ts,observed_m,predicted_m,surge_m\n"
        for ts, obs, pred in rows:
            yield f"{ts.isoformat()}Z,{obs},{pred},{round(obs - pred, 3)}\n"

    filename = f"tideline_{station.id}_{days}d.csv"
    return StreamingResponse(
        csv_lines(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _series_response(db, client, station, product, begin, end) -> SeriesOut:
    try:
        result = get_series(db, client, station, product, begin, end)
    except UpstreamUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SeriesOut(
        station_id=station.id,
        product=product,
        source=result.source,
        fetched_at=result.fetched_at,
        readings=[ReadingOut.model_validate(r) for r in result.readings],
    )
