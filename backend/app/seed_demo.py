"""Populate the database with realistic synthetic tide data.

Lets a reviewer run the whole app — map, charts, surge history, CSV export —
with no NOAA access at all. The generated series are physically plausible
rather than real: a semidiurnal (M2) tide plus a smaller diurnal (K1)
component for the astronomical *prediction*, and an *observed* level equal to
that prediction plus a slowly varying **surge residual** (the storm-and-wind
signal this app exists to surface) and a little measurement noise.

Fetch-log rows are written as "just refreshed" for every (station, product),
so `/overview` and the series endpoints serve entirely from the database and
never reach for NOAA.

    python -m app.seed_demo            # 14 days into a fresh database
    python -m app.seed_demo --days 30
"""

import argparse
import math
import random
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, ensure_schema
from .models import FetchLog, Reading, Station
from .seed import seed_stations
from .service import MAX_LOOKBACK_HOURS, OVERVIEW_PRODUCTS, PREDICTIONS_LOOKAHEAD_HOURS, utcnow

STEP = timedelta(minutes=6)  # NOAA's native observation cadence
PRODUCTS = (*OVERVIEW_PRODUCTS, "water_temperature")

# Tidal constituents (period in hours, amplitude in metres).
M2_PERIOD_H = 12.4206  # principal lunar semidiurnal
K1_PERIOD_H = 23.9345  # lunisolar diurnal
M2_AMPLITUDE = 0.62
K1_AMPLITUDE = 0.21
MEAN_LEVEL = 1.55  # metres above MLLW, roughly mid-range for the seeded stations


def _prediction(hours: float, phase: float) -> float:
    """Astronomical tide height at `hours` past the epoch for a station phase."""
    m2 = M2_AMPLITUDE * math.sin(2 * math.pi * hours / M2_PERIOD_H + phase)
    k1 = K1_AMPLITUDE * math.sin(2 * math.pi * hours / K1_PERIOD_H + phase / 2)
    return MEAN_LEVEL + m2 + k1


def _surge(hours: float, storm_at: float, storm_width: float, jitter: float) -> float:
    """A smooth surge residual: gentle background wander plus one storm bump."""
    background = 0.06 * math.sin(2 * math.pi * hours / 37.0 + jitter)
    storm = 0.35 * math.exp(-(((hours - storm_at) / storm_width) ** 2))
    return background + storm


def _station_phase(station_id: str) -> float:
    """A stable per-station tide phase so stations aren't all in lockstep."""
    return (int(station_id) % 360) * math.pi / 180.0


def seed_demo(db: Session, days: int = 14, seed: int = 1234) -> int:
    """Reset readings and fill the database with `days` of synthetic history.

    Returns the number of reading rows written. Existing readings and fetch-log
    rows are cleared first, so the result is a clean, reproducible demo state.
    """
    seed_stations(db)
    db.execute(delete(Reading))
    db.execute(delete(FetchLog))

    now = utcnow().replace(second=0, microsecond=0)
    now -= timedelta(minutes=now.minute % 6)  # align to the 6-minute grid
    start = now - timedelta(hours=MAX_LOOKBACK_HOURS) - timedelta(days=days)
    pred_end = now + timedelta(hours=PREDICTIONS_LOOKAHEAD_HOURS)

    rng = random.Random(seed)
    written = 0
    for station in db.scalars(select(Station).order_by(Station.id)):
        phase = _station_phase(station.id)
        jitter = rng.random() * math.pi
        storm_at = int(station.id) % (days * 24) + 12  # deterministic hour past `start`
        rows: list[Reading] = []

        t = start
        while t <= pred_end:
            hours = (t - start).total_seconds() / 3600.0
            predicted = _prediction(hours, phase)
            rows.append(
                Reading(
                    station_id=station.id, product="predictions", ts=t, value=round(predicted, 3)
                )
            )
            if t <= now:  # observations only exist up to "now"
                observed = predicted + _surge(hours, storm_at, 8.0, jitter) + rng.gauss(0, 0.015)
                temp = 16.0 + 3.0 * math.sin(2 * math.pi * hours / 24.0) + rng.gauss(0, 0.1)
                rows.append(
                    Reading(
                        station_id=station.id, product="water_level", ts=t, value=round(observed, 3)
                    )
                )
                rows.append(
                    Reading(
                        station_id=station.id,
                        product="water_temperature",
                        ts=t,
                        value=round(temp, 2),
                    )
                )
            t += STEP

        db.add_all(rows)
        written += len(rows)

    for station in db.scalars(select(Station)):
        for product in PRODUCTS:
            db.add(FetchLog(station_id=station.id, product=product, fetched_at=now))
    db.commit()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Tideline with synthetic demo data.")
    parser.add_argument("--days", type=int, default=14, help="days of history to generate")
    parser.add_argument("--seed", type=int, default=1234, help="RNG seed for reproducibility")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    ensure_schema(engine)
    with SessionLocal() as db:
        rows = seed_demo(db, days=args.days, seed=args.seed)
        stations = db.scalar(select(func.count()).select_from(Station))
    print(f"Seeded {rows} readings across {stations} stations ({args.days} days of history).")


if __name__ == "__main__":
    main()
