from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer


def _iso_utc(ts: datetime) -> str:
    """Serialize naive-UTC storage timestamps with an explicit Z suffix."""
    return ts.isoformat() + "Z"


class StationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    state: str
    lat: float
    lon: float
    # NWS coastal flood thresholds, meters above MLLW
    flood_minor: float | None
    flood_moderate: float | None
    flood_major: float | None


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    value: float

    @field_serializer("ts")
    def serialize_ts(self, ts: datetime) -> str:
        return _iso_utc(ts)


class StationOverviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    station: StationOut
    ts: datetime | None
    observed: float | None
    predicted: float | None
    surge: float | None
    flood_stage: Literal["minor", "moderate", "major"] | None

    @field_serializer("ts")
    def serialize_ts(self, ts: datetime | None) -> str | None:
        return _iso_utc(ts) if ts else None


class OverviewOut(BaseModel):
    stations: list[StationOverviewOut]


class DailySurgeOut(BaseModel):
    """One day of surge residual statistics from accumulated history."""

    day: date
    avg_surge: float
    max_surge: float
    samples: int


class SeriesOut(BaseModel):
    station_id: str
    product: str
    source: Literal["noaa", "cache", "stale"]
    fetched_at: datetime | None
    readings: list[ReadingOut]

    @field_serializer("fetched_at")
    def serialize_fetched_at(self, fetched_at: datetime | None) -> str | None:
        return _iso_utc(fetched_at) if fetched_at else None
