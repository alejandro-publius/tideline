"""Publishing side of the telemetry event path (see ADR 0007).

A reading that has just been stored is announced to a RabbitMQ *exchange*. The
exchange is a router: publishers hand it a message plus a routing key, and it
decides which queues get a copy. Publishing to an exchange rather than straight
to a queue is what lets a new consumer show up later, bind its own queue, and
start receiving readings without a single line changing here.

Publishing never raises. Reads are served from the database and must not start
failing because a broker is down; a failed publish means "no new anomaly rows
for that batch", which is a degradation, not an outage.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime

import pika
from pika.exceptions import AMQPError

from .config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadingEvent:
    """One observation, as it travels over the wire.

    Deliberately a flat, primitive-only record rather than the SQLAlchemy model:
    a consumer in another process (or another language) should not need to know
    anything about our ORM to read it.
    """

    station_id: str
    product: str
    ts: str  # ISO-8601, naive UTC — matches ADR 0003
    value: float

    @classmethod
    def build(cls, station_id: str, product: str, ts: datetime, value: float) -> ReadingEvent:
        return cls(station_id=station_id, product=product, ts=ts.isoformat(), value=value)

    @property
    def routing_key(self) -> str:
        """Routing keys are `reading.<product>`.

        A consumer binds with a pattern: `reading.water_level` for just those, or
        `reading.*` for every product. The publisher stays unaware of either.
        """
        return f"reading.{self.product}"


class ReadingPublisher:
    """Holds one broker connection and publishes reading events onto it.

    pika connections are not thread-safe and the history sweep fetches in a
    thread pool, so every publish is serialised behind a lock. At this message
    volume that costs nothing; a busier system would use a connection per thread.
    """

    def __init__(self, url: str, exchange: str, timeout: float) -> None:
        self._url = url
        self._exchange = exchange
        self._timeout = timeout
        self._lock = threading.Lock()
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    def _connect(self) -> None:
        """Open a connection and declare the exchange.

        Declaring is idempotent: whoever gets there first creates it, everyone
        after that confirms it matches. That means neither the publisher nor the
        consumer has to be started "first", which is one less operational rule.
        """
        parameters = pika.URLParameters(self._url)
        parameters.socket_timeout = self._timeout
        parameters.blocked_connection_timeout = self._timeout
        self._connection = pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=self._exchange,
            exchange_type="topic",
            durable=True,  # survives a broker restart
        )

    def _ensure_channel(self) -> pika.adapters.blocking_connection.BlockingChannel:
        if self._connection is None or self._connection.is_closed:
            self._connect()
        assert self._channel is not None
        return self._channel

    def publish(self, events: list[ReadingEvent]) -> int:
        """Publish a batch, returning how many were sent.

        Returns 0 rather than raising if the broker is unreachable.
        """
        if not events:
            return 0

        with self._lock:
            try:
                channel = self._ensure_channel()
                for event in events:
                    channel.basic_publish(
                        exchange=self._exchange,
                        routing_key=event.routing_key,
                        body=json.dumps(asdict(event)).encode(),
                        properties=pika.BasicProperties(
                            content_type="application/json",
                            # delivery_mode=2 writes the message to disk, so a
                            # broker restart does not silently drop the backlog.
                            delivery_mode=2,
                        ),
                    )
            except (AMQPError, OSError) as exc:
                # Drop the connection so the next publish reconnects cleanly.
                self._reset()
                logger.warning(
                    "reading publish failed, continuing without it",
                    extra={"error": str(exc), "events": len(events)},
                )
                return 0
            return len(events)

    def _reset(self) -> None:
        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except Exception:
            # Teardown must not mask whatever failure led us here, and the
            # connection is being discarded regardless, so this is logged at
            # debug rather than raised or swallowed silently.
            logger.debug("error closing broker connection during reset", exc_info=True)
        self._connection = None
        self._channel = None

    def close(self) -> None:
        with self._lock:
            self._reset()


_publisher: ReadingPublisher | None = None
_publisher_lock = threading.Lock()


def get_publisher() -> ReadingPublisher | None:
    """The process-wide publisher, or None when no broker is configured.

    A None publisher is the supported "just run the API" mode: tests and local
    development work with no broker installed.
    """
    global _publisher
    settings = get_settings()
    if not settings.broker_url:
        return None
    if _publisher is None:
        with _publisher_lock:
            if _publisher is None:
                _publisher = ReadingPublisher(
                    settings.broker_url,
                    settings.broker_exchange,
                    settings.broker_publish_timeout_seconds,
                )
    return _publisher
