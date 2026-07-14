# ADR 0001: Read-through cache in front of NOAA, not scheduled ingestion

**Status:** accepted (July 2026)

## Context

Every dashboard view needs recent NOAA CO-OPS data. NOAA is a public API with
informal rate expectations, occasional outages, and scheduled maintenance
windows. Two obvious shapes: a cron-style ingester that polls NOAA on a fixed
schedule and the API only ever reads the database, or a read-through cache
where requests trigger fetches when data is stale.

## Decision

Read-through cache, with freshness tracked per `(station, product)` in a
fetch log (TTL: 10 minutes for observations, 12 hours for predictions).
Two supporting rules:

- A cache miss always fetches the **full 72-hour window**, never just the
  requested range — otherwise a narrow request could mark a wide range fresh
  while the database holds only a sliver of it.
- Fetched rows are **upserted**, so history accumulates across pulls and
  re-fetches never duplicate rows.

A background sweep (every 30 minutes, configurable) keeps history
accumulating when nobody is visiting; it reuses the exact same cache path
rather than being a second ingestion system.

## Consequences

- Traffic to NOAA is proportional to distinct stale series, not to request
  volume — a popular station costs one upstream call per TTL window.
- The first visitor after a TTL expiry pays the fetch latency. Acceptable at
  this scale; a scheduled pre-warm is the escape hatch if it ever isn't.
- When NOAA is down, the cache **is** the fallback: data is served flagged
  `stale` instead of erroring (see the `source` field in series responses).
