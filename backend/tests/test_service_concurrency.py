"""The write path must be idempotent under concurrent refreshes.

Multiple sessions (requests and the background sweep) can all find the same
(station, product) stale, fetch in parallel, and race the insert; losers trip
unique constraints. These tests force those interleavings deterministically —
commits raise IntegrityError the way a lost race does — and assert the writers
recover instead of surfacing a 500.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import service
from app.models import FetchLog, Reading
from app.service import utcnow


def _integrity_error() -> IntegrityError:
    return IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed"))


def test_store_retries_and_dedupes_against_the_winners_rows(db, monkeypatch):
    """When the commit trips the unique constraint, _store must roll back,
    re-read what the winner committed, and insert only the still-missing rows."""
    ts1, ts2 = datetime(2026, 7, 9, 10, 0), datetime(2026, 7, 9, 10, 6)
    series = [(ts1, 1.5), (ts2, 1.6)]
    real_commit = db.commit
    state = {"raced": False}

    def flaky_commit():
        if not state["raced"]:
            state["raced"] = True
            db.rollback()  # discard the loser's pending inserts
            # the winner lands one overlapping row between our SELECT and commit
            db.add(Reading(station_id="9414290", product="water_level", ts=ts1, value=1.5))
            real_commit()
            raise _integrity_error()
        real_commit()

    monkeypatch.setattr(db, "commit", flaky_commit)
    service._store(db, "9414290", "water_level", series)

    rows = db.query(Reading).filter_by(station_id="9414290", product="water_level").all()
    assert sorted(r.ts for r in rows) == [ts1, ts2], "no duplicates, no missing rows"


def test_store_reraises_after_persistent_conflicts(db, monkeypatch):
    """Retries are bounded: a pathologically racy pair surfaces the error
    instead of looping forever."""
    monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(_integrity_error()))

    with pytest.raises(IntegrityError):
        service._store(db, "9414290", "water_level", [(datetime(2026, 7, 9, 10, 0), 1.5)])


def test_touch_log_survives_losing_an_insert_race(db, monkeypatch):
    """If the fetch-log insert loses the primary-key race, _touch_log must
    update the winner's row rather than propagate the IntegrityError."""
    now = utcnow().replace(microsecond=0)
    real_commit = db.commit
    state = {"raced": False}

    def flaky_commit():
        if not state["raced"]:
            state["raced"] = True
            db.rollback()  # discard the loser's pending insert
            # the winner's row lands between our lookup and our commit
            db.add(
                FetchLog(
                    station_id="9414290",
                    product="water_level",
                    fetched_at=now - timedelta(minutes=5),
                )
            )
            real_commit()
            raise _integrity_error()
        real_commit()

    monkeypatch.setattr(db, "commit", flaky_commit)
    log = service._touch_log(db, None, "9414290", "water_level", now)

    assert log.fetched_at == now
    assert db.get(FetchLog, ("9414290", "water_level")).fetched_at == now
