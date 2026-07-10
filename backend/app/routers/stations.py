from datetime import timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Station
from ..noaa import NoaaClient
from ..schemas import SeriesOut, StationOut
from ..service import UpstreamUnavailable, get_series, utcnow

router = APIRouter(prefix="/api/stations", tags=["stations"])


class ObservedProduct(str, Enum):
    water_level = "water_level"
    water_temperature = "water_temperature"


def get_noaa_client() -> NoaaClient:
    return NoaaClient(get_settings().noaa_base_url)


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
    hours: int = Query(default=24, ge=1, le=48),
    db: Session = Depends(get_db),
    client: NoaaClient = Depends(get_noaa_client),
) -> SeriesOut:
    """Astronomical tide predictions from `hours` ago to `hours` ahead.

    The window extends into the future so the UI can chart the upcoming tide
    alongside what was observed.
    """
    station = _get_station(db, station_id)
    now = utcnow()
    delta = timedelta(hours=hours)
    return _series_response(db, client, station, "predictions", now - delta, now + delta)


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
        readings=result.readings,
    )
