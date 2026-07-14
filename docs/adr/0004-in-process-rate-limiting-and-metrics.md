# ADR 0004: Rate limiting and metrics in-process — no Redis, no client library

**Status:** accepted (July 2026)

## Context

A public API needs abuse protection and operational visibility. The standard
enterprise answer is Redis-backed rate limiting and a Prometheus client
library. This app is a single process serving a single deployment.

## Decision

Both concerns live in-process:

- **Rate limiting** is a token bucket per client (`ratelimit.py`): burst up
  to the per-minute budget, continuous refill, `429` + `Retry-After` beyond
  it. `/api/healthz` is exempt so a throttled client can never make the
  platform's health check think the service is down. The bucket map is
  pruned so a client cycling source addresses can't grow it without bound —
  the limiter must not be its own memory-exhaustion vector.
- **Client identity** prefers the first `X-Forwarded-For` hop because the
  production deployment sits behind Render's proxy, which sets it. Without a
  trusted proxy that header is spoofable; the socket address is the fallback.
  A multi-proxy deployment would need a configurable trusted-hop count.
- **Metrics** are hand-rolled counters (`metrics.py`) exposed at
  `/api/metrics` in Prometheus text format. Request labels use the matched
  route *template*, not the raw path, so station ids and scanner probes can't
  mint unbounded label values.

## Consequences

- Zero new dependencies and no infrastructure to run; both modules are ~100
  lines and fully unit-tested with a fake clock.
- The limits are per-process. Scaling to N replicas divides the effective
  budget by N and makes it inconsistent — at that point the limiter's
  interface is the seam where a shared store (Redis) slots in, and the
  metrics endpoint gains per-instance labels via the scrape config.
- Counters only (no histograms). Latency percentiles are the first thing a
  real prometheus-client migration would add.
