from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Station(Base):
    """A NOAA CO-OPS observation station."""

    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(2))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)

    readings: Mapped[list["Reading"]] = relationship(back_populates="station")


class Reading(Base):
    """One (station, product, timestamp) value pulled from NOAA.

    All timestamps are stored as naive UTC.
    """

    __tablename__ = "readings"
    __table_args__ = (UniqueConstraint("station_id", "product", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), index=True)
    product: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    value: Mapped[float] = mapped_column(Float)

    station: Mapped[Station] = relationship(back_populates="readings")


class FetchLog(Base):
    """When each (station, product) series was last refreshed from NOAA."""

    __tablename__ = "fetch_log"

    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), primary_key=True)
    product: Mapped[str] = mapped_column(String(32), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
