"""Consuming side of the telemetry event path (see ADR 0007).

Runs as its own process: `python -m app.detector`. It subscribes to reading
events, decides whether each one crossed a flood threshold, and records the ones
that did. Nothing here is on the HTTP request path, which is the entire point —
the API keeps serving whether or not this process is alive, and this process
keeps working through an API deploy.

Delivery is at-least-once. A message is acknowledged only after its work is
committed, so a crash mid-message means the broker hands that message back on
restart rather than losing it.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from datetime import datetime
from types import FrameType

import pika
from pika.exceptions import AMQPError
from sqlalchemy.orm import Session

from . import metrics
from .config import get_settings
from .database import make_engine
from .logging_config import configure_logging
from .models import Anomaly, Station
from .service import flood_stage, utcnow

logger = logging.getLogger("tideline.detector")

QUEUE_NAME = "anomaly.detector"
# Bind to every product; only water_level currently yields a verdict, but a new
# product starts flowing here without a broker change.
BINDING_KEY = "reading.*"

# How many unacknowledged messages the broker will hand us at once. Without this
# RabbitMQ pushes the entire queue at a single consumer, which defeats running a
# second one and lets one slow consumer hoard the backlog.
PREFETCH_COUNT = 16


def evaluate(db: Session, station_id: str, product: str, ts: datetime, value: float) -> str | None:
    """Return the severity this reading crossed, or None if it is unremarkable."""
    if product != "water_level":
        return None
    station = db.get(Station, station_id)
    if station is None:
        # A reading for a station we do not know about is not an error worth
        # retrying — the detector simply has no thresholds to judge it against.
        logger.warning("reading for unknown station", extra={"station": station_id})
        return None
    return flood_stage(value, station)


def record(
    db: Session, station_id: str, product: str, ts: datetime, value: float, severity: str
) -> None:
    """Persist one anomaly."""
    db.add(
        Anomaly(
            station_id=station_id,
            product=product,
            ts=ts,
            value=value,
            severity=severity,
            detected_at=utcnow(),
        )
    )
    db.commit()


def handle_message(db: Session, body: bytes) -> None:
    """Process one reading event. Raising here means the message is not acked."""
    payload = json.loads(body)
    station_id = payload["station_id"]
    product = payload["product"]
    ts = datetime.fromisoformat(payload["ts"])
    value = float(payload["value"])

    severity = evaluate(db, station_id, product, ts, value)
    if severity is None:
        metrics.ANOMALY_EVENTS.inc(result="clear")
        return

    record(db, station_id, product, ts, value, severity)
    metrics.ANOMALY_EVENTS.inc(result="detected")
    logger.info(
        "anomaly recorded",
        extra={"station": station_id, "severity": severity, "value": value},
    )


def run() -> None:
    """Connect, subscribe, and process messages until interrupted."""
    configure_logging()
    settings = get_settings()
    if not settings.broker_url:
        logger.error("TIDELINE_BROKER_URL is not set; the detector has nothing to consume")
        sys.exit(1)

    engine = make_engine(settings.database_url)

    connection = pika.BlockingConnection(pika.URLParameters(settings.broker_url))
    channel = connection.channel()
    # Both sides declare the topology, so neither has to start first.
    channel.exchange_declare(settings.broker_exchange, exchange_type="topic", durable=True)
    channel.queue_declare(QUEUE_NAME, durable=True)
    channel.queue_bind(QUEUE_NAME, settings.broker_exchange, routing_key=BINDING_KEY)
    channel.basic_qos(prefetch_count=PREFETCH_COUNT)

    def on_message(ch, method, properties, body: bytes) -> None:
        with Session(engine) as db:
            handle_message(db, body)
        # Acknowledged only now, after the work is committed. Ack earlier and a
        # crash in between would lose the reading silently.
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    def stop(signum: int, frame: FrameType | None) -> None:
        # Finish the message in flight, then break out of the consume loop, so
        # shutdown does not manufacture a redelivery.
        logger.info("shutting down")
        channel.stop_consuming()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    logger.info("detector listening", extra={"queue": QUEUE_NAME, "binding": BINDING_KEY})
    try:
        channel.start_consuming()
    except AMQPError:
        logger.exception("broker connection failed")
        sys.exit(1)
    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    run()
