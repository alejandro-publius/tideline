"""Consuming side of the telemetry event path (see ADR 0007).

Runs as its own process: `python -m app.detector`. It subscribes to reading
events and judges each one two ways — against the station's absolute flood
thresholds, and against what the tide tables predicted for that moment — then
records whatever it finds. Nothing here is on the HTTP request path, which is
the entire point: the API keeps serving whether or not this process is alive,
and this process keeps working through an API deploy.

Delivery is at-least-once. A message is acknowledged only after its work is
committed, so a crash mid-message means the broker hands that message back on
restart rather than losing it.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from types import FrameType

import pika
from pika.exceptions import AMQPError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import metrics
from .config import get_settings
from .database import make_engine
from .logging_config import configure_logging
from .models import Anomaly, Reading, Station
from .service import flood_stage, utcnow

logger = logging.getLogger("tideline.detector")

QUEUE_NAME = "anomaly.detector"
# Bind to every product; only water_level currently yields a verdict, but a new
# product starts flowing here without a broker change.
BINDING_KEY = "reading.*"
# Messages the detector can never process are parked here for a human to look at.
DEAD_LETTER_QUEUE = "anomaly.detector.dead"

# How many unacknowledged messages the broker will hand us at once. Without this
# RabbitMQ pushes the entire queue at a single consumer, which defeats running a
# second one and lets one slow consumer hoard the backlog.
PREFETCH_COUNT = 16


class Unprocessable(Exception):
    """The message will never succeed, however many times it is redelivered.

    Distinct from an ordinary failure. If the database is briefly unreachable the
    right response is to let the message come back and try again; if the payload
    is malformed, retrying is an infinite loop that also blocks everything queued
    behind it. Only this exception sends a message to the dead-letter queue.
    """


@dataclass(frozen=True)
class Verdict:
    """One judgement about a reading. `residual` is set only for surge."""

    kind: str
    severity: str
    residual: float | None = None


def evaluate_flood(station: Station, value: float) -> Verdict | None:
    """Absolute check: did the level cross a published NWS flood threshold?"""
    severity = flood_stage(value, station)
    return None if severity is None else Verdict(kind="flood", severity=severity)


def evaluate_surge(
    db: Session, station_id: str, ts: datetime, value: float, threshold: float
) -> Verdict | None:
    """Relative check: is the level far from what the tide tables predicted?

    Tides are astronomy and therefore predictable years ahead, so the residual
    (observed - predicted) isolates whatever the tide tables cannot see — storm
    surge, wind setup, pressure anomalies. This catches events an absolute
    threshold cannot: the same 1.4 m is unremarkable at high tide and alarming
    at low tide.

    Returns None when there is no prediction for that timestamp; a missing
    prediction is an absence of evidence, not evidence of calm.
    """
    predicted = db.scalar(
        select(Reading.value).where(
            Reading.station_id == station_id,
            Reading.product == "predictions",
            Reading.ts == ts,
        )
    )
    if predicted is None:
        return None

    residual = round(value - predicted, 3)
    if abs(residual) < threshold:
        return None
    return Verdict(
        kind="surge",
        severity="above" if residual > 0 else "below",
        residual=residual,
    )


def evaluate(
    db: Session, station_id: str, product: str, ts: datetime, value: float
) -> list[Verdict]:
    """Every judgement that applies to this reading. May be empty."""
    if product != "water_level":
        return []
    station = db.get(Station, station_id)
    if station is None:
        # A reading for a station we do not know about is not an error worth
        # retrying — the detector simply has no thresholds to judge it against.
        logger.warning("reading for unknown station", extra={"station": station_id})
        return []

    threshold = get_settings().surge_threshold_m
    candidates = [
        evaluate_flood(station, value),
        evaluate_surge(db, station_id, ts, value, threshold),
    ]
    return [verdict for verdict in candidates if verdict is not None]


def record(
    db: Session, station_id: str, product: str, ts: datetime, value: float, verdicts: list[Verdict]
) -> int:
    """Persist the verdicts for one reading, skipping any already recorded.

    This has to be idempotent, because at-least-once delivery guarantees we will
    sometimes see the same reading twice: a consumer that commits its work and
    then dies before acknowledging is handed that message again on restart.

    Verdicts are a pure function of the reading, so a second look reaches the
    same conclusion and there is nothing to update — the existing row is already
    correct. Returns the number of rows actually written.
    """
    already_recorded = set(
        db.scalars(
            select(Anomaly.kind).where(
                Anomaly.station_id == station_id,
                Anomaly.product == product,
                Anomaly.ts == ts,
            )
        )
    )
    new = [verdict for verdict in verdicts if verdict.kind not in already_recorded]
    if not new:
        return 0

    db.add_all(
        Anomaly(
            station_id=station_id,
            product=product,
            ts=ts,
            value=value,
            kind=verdict.kind,
            severity=verdict.severity,
            residual=verdict.residual,
            detected_at=utcnow(),
        )
        for verdict in new
    )
    try:
        db.commit()
    except IntegrityError:
        # The check above is not atomic, so two consumers handling the same
        # redelivered reading can both pass it. The unique constraint is the real
        # guarantee; losing that race just means the row already exists.
        db.rollback()
        logger.debug(
            "anomaly already recorded by another consumer",
            extra={"station": station_id, "ts": ts.isoformat()},
        )
        return 0
    return len(new)


def parse(body: bytes) -> tuple[str, str, datetime, float]:
    """Read one event off the wire.

    Every failure here is a property of the bytes themselves, so no amount of
    retrying will help — they are raised as Unprocessable and dead-lettered.
    """
    try:
        payload = json.loads(body)
        return (
            str(payload["station_id"]),
            str(payload["product"]),
            datetime.fromisoformat(payload["ts"]),
            float(payload["value"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise Unprocessable(f"malformed reading event: {exc}") from exc


def handle_message(db: Session, body: bytes) -> None:
    """Process one reading event.

    Raising Unprocessable means the message is dead-lettered. Any other exception
    means the message is left unacknowledged and will be retried.
    """
    station_id, product, ts, value = parse(body)

    verdicts = evaluate(db, station_id, product, ts, value)
    if not verdicts:
        metrics.ANOMALY_EVENTS.inc(result="clear")
        return

    written = record(db, station_id, product, ts, value, verdicts)
    if not written:
        # A redelivery of something already handled. Normal under at-least-once,
        # worth counting so a spike in redeliveries is visible.
        metrics.ANOMALY_EVENTS.inc(result="duplicate")
        return

    for verdict in verdicts:
        metrics.ANOMALY_EVENTS.inc(result=verdict.kind)
    logger.info(
        "anomaly recorded",
        extra={
            "station": station_id,
            "value": value,
            "verdicts": ",".join(f"{v.kind}:{v.severity}" for v in verdicts),
        },
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

    # Rejected messages are republished to the dead-letter exchange, which fans
    # them into one holding queue. Note that queue arguments are immutable once a
    # queue exists: adding dead-lettering to a live deployment means draining and
    # redeclaring, not editing in place.
    channel.exchange_declare(
        settings.broker_dead_letter_exchange, exchange_type="fanout", durable=True
    )
    channel.queue_declare(DEAD_LETTER_QUEUE, durable=True)
    channel.queue_bind(DEAD_LETTER_QUEUE, settings.broker_dead_letter_exchange)

    channel.queue_declare(
        QUEUE_NAME,
        durable=True,
        arguments={"x-dead-letter-exchange": settings.broker_dead_letter_exchange},
    )
    channel.queue_bind(QUEUE_NAME, settings.broker_exchange, routing_key=BINDING_KEY)
    channel.basic_qos(prefetch_count=PREFETCH_COUNT)

    def on_message(ch, method, properties, body: bytes) -> None:
        try:
            with Session(engine) as db:
                handle_message(db, body)
        except Unprocessable as exc:
            # requeue=False is what routes this to the dead-letter exchange.
            # Retrying would loop forever and block everything behind it.
            logger.error(
                "dead-lettering unprocessable message",
                extra={"error": str(exc), "body": body[:200].decode(errors="replace")},
            )
            metrics.ANOMALY_EVENTS.inc(result="dead_lettered")
            ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            return
        except Exception:
            # Anything else is assumed transient — a database blip, say. Return
            # it to the queue so a later attempt, or another consumer, can try.
            logger.exception("transient failure, returning message to the queue")
            metrics.ANOMALY_EVENTS.inc(result="requeued")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return

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
