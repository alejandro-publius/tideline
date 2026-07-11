# ADR 0005: Retry only transient NOAA failures, with exponential backoff

**Status:** accepted (July 2026)

## Context

NOAA CO-OPS is occasionally flaky: connection resets, timeouts, brief 5xx
bursts, and scheduled maintenance pages served as HTML with a 200 status.
Naive retry-everything policies amplify outages (retrying a deterministic
failure just adds latency and load) and can hammer a struggling upstream.

## Decision

Classify failures before retrying (`noaa.py`):

- **Transient — retry with exponential backoff:** network/transport errors
  and 5xx responses. Up to `TIDELINE_NOAA_MAX_RETRIES` attempts, waiting
  `backoff_base × 2^(attempt−1)` between tries.
- **Deterministic — fail immediately:** 4xx responses, NOAA error payloads,
  and non-JSON bodies. These won't fix themselves within a retry window; the
  caller's stale-cache fallback (ADR 0001) is the right degradation, not a
  retry loop.
- "No data was found" is not a failure at all — it's a valid empty answer
  (some stations simply lack a sensor for a product).

Identical requests are also memoized per client instance for a short TTL, so
one overview sweep never fetches the same series twice.

## Consequences

- A single NOAA hiccup is invisible to users; a real outage degrades to
  `stale`-flagged data after bounded attempts instead of hanging requests.
- Retries multiply worst-case latency; the bounds are configurable and the
  retry count is observable (`tideline_noaa_retries_total` in `/api/metrics`).
- Backoff is deterministic (no jitter). With ~13 stations on one process,
  synchronized retry stampedes aren't a realistic failure mode; jitter is the
  first addition if the fleet ever grows.
