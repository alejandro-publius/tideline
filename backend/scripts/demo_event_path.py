"""Run the whole event path end to end against a throwaway database.

    TIDELINE_BROKER_URL=amqp://guest:guest@localhost:5672/ \
        python -m scripts.demo_event_path

Seeds one station and its astronomical tide predictions, then feeds in
observations that run steadily above those predictions — a storm pushing water
onto the coast. Readings go in through the real service path, so they publish to
the broker exactly as production traffic would; the detector consumes them and
its findings are read back through the API.

The point of the demo is the ordering. Surge is flagged from the first reading
that diverges from the prediction, while the absolute NWS flood threshold is not
crossed until hours later. An absolute threshold answers "is the water high"; the
residual answers "is the water doing something the tide tables cannot explain",
and only the second one sees a storm coming.
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

DB_PATH = Path("demo_event_path.db")
STATION = "9414290"
START = datetime(2026, 8, 8, 12, 0)
HOURS = 6


def seed(engine) -> None:
    from app.models import Reading, Station

    with Session(engine) as db:
        db.add(
            Station(
                id=STATION,
                name="San Francisco",
                state="CA",
                lat=37.806305,
                lon=-122.46589,
                # Real NWS coastal flood thresholds, metres above MLLW.
                flood_minor=2.146,
                flood_moderate=2.633,
                flood_major=3.021,
            )
        )
        for hour in range(HOURS):
            db.add(
                Reading(
                    station_id=STATION,
                    product="predictions",
                    ts=START + timedelta(hours=hour),
                    value=0.5 + 0.1 * hour,
                )
            )
        db.commit()


def observed(hour: int) -> float:
    """Predicted tide plus a surge that builds quadratically, as a storm does."""
    return 0.5 + 0.1 * hour + 0.05 * hour * hour


def main() -> int:
    if not os.environ.get("TIDELINE_BROKER_URL"):
        print("TIDELINE_BROKER_URL is not set — start RabbitMQ and set it first.")
        return 1
    os.environ["TIDELINE_DATABASE_URL"] = f"sqlite:///./{DB_PATH}"

    from app import models  # noqa: F401 - registers the tables on Base.metadata
    from app.config import get_settings
    from app.database import Base, make_engine

    get_settings.cache_clear()
    DB_PATH.unlink(missing_ok=True)
    engine = make_engine(get_settings().database_url)
    Base.metadata.create_all(engine)
    seed(engine)
    print(f"seeded {STATION} with {HOURS}h of tide predictions\n")

    detector = subprocess.Popen(
        [sys.executable, "-m", "app.detector"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(3)  # let it declare its queue and subscribe

        from app.service import _store

        print("feeding observations that run above the predicted tide:")
        for hour in range(HOURS):
            ts = START + timedelta(hours=hour)
            value = observed(hour)
            print(f"  {ts:%H:%M}  predicted {0.5 + 0.1 * hour:.2f}  observed {value:.2f}")
            with Session(engine) as db:
                _store(db, STATION, "water_level", [(ts, value)])
        time.sleep(3)  # let the detector drain
    finally:
        detector.terminate()
        detector.wait(timeout=10)

    from fastapi.testclient import TestClient

    from app.main import app

    print("\nGET /api/anomalies")
    with TestClient(app) as client:
        for anomaly in reversed(client.get("/api/anomalies").json()["anomalies"]):
            residual = (
                f"  residual {anomaly['residual']:+.2f} m"
                if anomaly["residual"] is not None
                else ""
            )
            print(
                f"  {anomaly['ts'][11:16]}  {anomaly['kind']:<5} {anomaly['severity']:<8}{residual}"
            )

    print(
        "\nSurge is flagged from the first divergence; the absolute flood threshold\n"
        "is not crossed until the final reading. Same data, hours of difference."
    )
    DB_PATH.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
