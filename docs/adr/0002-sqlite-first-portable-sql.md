# ADR 0002: SQLite by default, portable SQL so Postgres is a config change

**Status:** accepted (July 2026)

## Context

The app needs durable storage for readings, stations, and the fetch log. The
free hosting tier has an ephemeral disk; a managed Postgres is available but
adds setup friction for anyone cloning the repo.

## Decision

Default to SQLite (`sqlite:///./tideline.db`) and treat the database as
swappable: all queries go through SQLAlchemy with no dialect-specific SQL —
the "upsert" is a portable insert-if-absent rather than SQLite's
`ON CONFLICT`. Switching to Postgres is exactly one environment variable
(`TIDELINE_DATABASE_URL`).

The claim is enforced, not aspirational: CI runs the full test suite twice,
once on in-memory SQLite and once against a real `postgres:16` service.

## Consequences

- `git clone` → running app with zero database setup; deploys that need
  durability point the URL at Postgres.
- The portable upsert is two statements (SELECT existing, INSERT missing)
  instead of one native upsert. At ~13 stations × 6-minute data this is
  irrelevant; at real scale, the native statement per dialect is the known
  optimization to reach for.
- SQLite's single-writer model is fine here because writes are serialized
  through the cache service; anything more concurrent should flip to
  Postgres first and only then get clever.
