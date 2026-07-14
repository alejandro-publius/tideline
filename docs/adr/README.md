# Architecture Decision Records

Short records of the decisions that shaped Tideline — what was decided, what
was rejected, and what it costs. Each one is written when the decision is
made, not reverse-engineered later; if a decision is revisited, the record
gets superseded rather than rewritten.

| ADR | Decision |
|---|---|
| [0001](0001-read-through-cache.md) | Read-through cache in front of NOAA, not scheduled ingestion |
| [0002](0002-sqlite-first-portable-sql.md) | SQLite by default, portable SQL so Postgres is a config change |
| [0003](0003-naive-utc-timestamps.md) | Naive UTC everywhere inside; explicit `Z` at the serialization boundary |
| [0004](0004-in-process-rate-limiting-and-metrics.md) | Rate limiting and metrics in-process, no Redis / no client library |
| [0005](0005-retry-only-transient-noaa-failures.md) | Retry only transient NOAA failures, with exponential backoff |
