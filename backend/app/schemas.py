from datetime import datetime
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


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    value: float

    @field_serializer("ts")
    def serialize_ts(self, ts: datetime) -> str:
        return _iso_utc(ts)


class SeriesOut(BaseModel):
    station_id: str
    product: str
    source: Literal["noaa", "cache", "stale"]
    fetched_at: datetime | None
    readings: list[ReadingOut]

    @field_serializer("fetched_at")
    def serialize_fetched_at(self, fetched_at: datetime | None) -> str | None:
        return _iso_utc(fetched_at) if fetched_at else None
