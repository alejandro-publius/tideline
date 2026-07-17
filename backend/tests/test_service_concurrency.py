"""The write path must be idempotent under concurrent refreshes.

Two sessions (a request and the background sweep, or two parallel requests)
can both find the same (station, product) stale, both fetch, and race the
insert; the loser trips a unique constraint. These tests force that exact
interleaving deterministically — the first commit raises IntegrityError the
way a lost race does — and assert the writers recover instead of surfacing
a 500.
"""

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app import service
from app.models import FetchLog, Reading
from app.service import utcnow


def _integrity_error() -> IntegrityError:
    return IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed"))


def test_store_survives_losing_an_insert_race(db, monkeypatch):
    """If the commit trips the unique constraint (a concurrent writer won),
    _store must roll back, re-read what the winner committed, and retry."""
    series = [(datetime(2026, 7, 9, 10, 0), 1.5), (datetime(2026, 7, 9, 10, 6), 1.6)]
    real_commit = db.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _integrity_error()
        real_commit()

    monkeypatch.setattr(db, "commit", flaky_commit)
    service._store(db, "9414290", "water_level", series)

    stored = db.query(Reading).filter_by(station_id="9414290", product="water_level").count()
    assert stored == 2
    assert calls["n"] == 2, "the writer must retry exactly once"


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
