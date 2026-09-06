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
    # NWS coastal flood thresholds in meters above MLLW (null = not defined)
    flood_minor: Mapped[float | None] = mapped_column(Float, nullable=True)
    flood_moderate: Mapped[float | None] = mapped_column(Float, nullable=True)
    flood_major: Mapped[float | None] = mapped_column(Float, nullable=True)

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


class Anomaly(Base):
    """A reading the detector judged notable, found on the event path (ADR 0007).

    Two independent kinds of judgement, because they answer different questions:

    - `flood` asks "is the absolute level dangerous", against the NWS thresholds.
    - `surge` asks "is the level far from what the tide tables predicted", which
      catches storm surge that an absolute threshold cannot: 1.4 m is unremarkable
      at high tide and alarming at low tide.

    One reading can raise both, so `kind` is part of the natural key. The key is
    the reading being described — (station, product, ts, kind) — not an arrival
    counter, because at-least-once delivery means the same reading can be
    processed more than once and must not produce a second row.
    """

    __tablename__ = "anomalies"
    __table_args__ = (UniqueConstraint("station_id", "product", "ts", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), index=True)
    product: Mapped[str] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    value: Mapped[float] = mapped_column(Float)
    # flood (crossed an absolute threshold) | surge (diverged from prediction)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    # flood: minor | moderate | major. surge: above | below (the prediction).
    severity: Mapped[str] = mapped_column(String(16))
    # observed - predicted, in metres. Null for flood anomalies.
    residual: Mapped[float | None] = mapped_column(Float, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime)


class FetchLog(Base):
    """When each (station, product) series was last refreshed from NOAA."""

    __tablename__ = "fetch_log"

    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), primary_key=True)
    product: Mapped[str] = mapped_column(String(32), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
