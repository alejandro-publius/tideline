# ADR 0003: Naive UTC everywhere inside; explicit `Z` at the boundary

**Status:** accepted (July 2026)

## Context

NOAA returns GMT timestamps. Browsers want local time. Databases differ in
how (and whether) they store timezone information — SQLite has no timezone
type at all, Postgres has two with famously confusing semantics. Mixing aware
and naive datetimes in Python raises at comparison time, but only sometimes.

## Decision

One rule: **every datetime inside the system is naive UTC.** NOAA responses
are parsed straight into naive UTC; the database stores naive columns on both
SQLite and Postgres; all arithmetic and comparisons happen in that one zone.
Timezone awareness exists only at the two edges:

- Serialization appends an explicit `Z` (`2026-07-09T10:00:00Z`) so clients
  never have to guess.
- The frontend converts to the viewer's local time at render.

## Consequences

- No aware-vs-naive `TypeError`s, no dialect-specific timezone behavior to
  test around, identical semantics on SQLite and Postgres.
- The discipline is invisible, so it's documented here and in the model
  docstrings — the one place a future contributor could break it is by
  storing a `datetime.now()` (local!) instead of `utcnow()`.
- If the system ever needs to store the *origin* timezone (it doesn't — tides
  are physics, not appointments), this decision gets superseded.
