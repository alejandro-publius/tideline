# Tideline: computing the surge residual

## The problem

A tide table is astronomy. Given a location and a moment, you can predict the
water level from the positions of the moon and sun — the semidiurnal and
diurnal constituents that NOAA publishes as **predictions**. That number is
correct in the sense that gravity is correct, and wrong in the sense that the
ocean does not only listen to gravity.

What actually shows up at a tide gauge — NOAA's **observed** water level — is
the astronomical tide *plus* everything the tables can't see: storm surge, wind
setup pushing water against the coast, atmospheric pressure anomalies, river
discharge. The difference between the two,

```
surge residual = observed − predicted
```

is the entire non-astronomical signal in one number. A calm day sits near zero.
A rising residual across a run of hours is the fingerprint of a storm, and it
climbs *before* the raw water level looks alarming, because it strips out the
tide that would have been high anyway. That residual is what Tideline exists to
compute and surface.

## Why it's harder than a subtraction

The arithmetic is trivial; making it trustworthy from a flaky public API is not.

**Two series, one instant.** Observed and predicted come from different NOAA
products with independent request paths. The residual only means something when
both are sampled at the *same* timestamp, so the system stores each product on
NOAA's native 6-minute grid and pairs them by exact timestamp — an observation
with no prediction at that instant is simply not a residual, and is dropped from
aggregates rather than guessed at.

**Missing and late readings.** Sensors drop out; NOAA returns empty `v` fields
for gaps and, during maintenance, sometimes a 200 with an HTML body instead of
JSON. Both are treated as absence, not as zero. A station with no sensor for a
product (San Francisco has no thermometer) is a valid empty answer, not an
error.

**Upstream that isn't always up.** NOAA rate-limits and occasionally times out.
Tideline never lets that reach the user as a failure if it can avoid it.

## How the system solves it

The core is a **read-through cache** (`backend/app/service.py`) sitting between
the REST API and NOAA:

- **Freshness per (station, product)** is tracked in a fetch log — 10 minutes
  for observations, 12 hours for predictions, since astronomy doesn't move.
- **Refreshes always pull the full 72-hour window**, never just the requested
  slice. Otherwise a narrow request could mark a wide range "fresh" while the
  database held only a sliver of it.
- **Readings are upserted**, so history *accumulates* across pulls and
  re-fetches never duplicate rows. A background sweep keeps this growing even
  with no visitors, which is what makes the daily-surge history and CSV export
  possible without a data pipeline.
- **When NOAA fails, the last good data is served with `source: "stale"`** and
  the UI says so, rather than erroring. Transient failures (network, 5xx) are
  retried with exponential backoff first; deterministic ones (4xx, error
  payloads) are surfaced immediately, because retrying them only adds latency.

On top of the residual, observed levels are classified against each station's
**NWS flood thresholds** (minor/moderate/major, in meters above MLLW), so the
map can say not just "anomalous" but "how anomalous relative to what floods
*here*."

## Honest limits

The predictions are NOAA's harmonic forecast, not a hydrodynamic model, so the
residual inherits NOAA's harmonic error — small in open water, larger in
complex estuaries. And a residual is a *detector*, not a *forecaster*: it tells
you a surge is happening, not how high it will get. Within those limits, it
turns two raw time series into the one signal a coastal reader actually wants.
