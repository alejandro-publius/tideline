"""Publisher tests (ADR 0007).

These run without a broker installed. The behaviour that matters here is the
contract around publishing, not pika's wire protocol: what gets sent, and that
a broken broker cannot take the read path down with it.
"""

from datetime import datetime

import pytest

from app import broker
from app.broker import ReadingEvent, ReadingPublisher, get_publisher


def test_event_routing_key_is_namespaced_by_product() -> None:
    event = ReadingEvent.build("9414290", "water_level", datetime(2026, 8, 8, 12, 0), 1.5)

    # Consumers bind on this: `reading.water_level` for one product, or
    # `reading.*` for all of them.
    assert event.routing_key == "reading.water_level"


def test_event_serialises_timestamps_as_iso_strings() -> None:
    event = ReadingEvent.build("9414290", "water_level", datetime(2026, 8, 8, 12, 0), 1.5)

    # A consumer in another process shouldn't need our ORM or Python's datetime
    # repr to read this.
    assert event.ts == "2026-08-08T12:00:00"
    assert event.value == 1.5


def test_publishing_nothing_does_not_open_a_connection() -> None:
    publisher = ReadingPublisher("amqp://guest:guest@localhost:5672/", "x", 0.1)

    # No broker is running in the test environment, so this would raise if it
    # tried to connect.
    assert publisher.publish([]) == 0


def test_publish_failure_is_swallowed_and_reported_as_zero() -> None:
    """A broker that cannot be reached must not raise into the read path."""
    # Port 1 is reserved and never listening.
    publisher = ReadingPublisher("amqp://guest:guest@127.0.0.1:1/", "x", 0.1)
    event = ReadingEvent.build("9414290", "water_level", datetime(2026, 8, 8, 12, 0), 1.5)

    assert publisher.publish([event]) == 0


def test_no_broker_configured_means_no_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running with no broker at all is a supported mode, not an error."""
    monkeypatch.setattr(broker, "_publisher", None)
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.delenv("TIDELINE_BROKER_URL", raising=False)

    assert get_publisher() is None

    get_settings.cache_clear()
