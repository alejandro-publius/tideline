# ADR 0007: Publish readings to a broker so anomaly detection runs independently of reads

**Status:** accepted (August 2026)

## Context

[ADR 0001](0001-read-through-cache.md) chose a read-through cache over scheduled
ingestion, and that decision still holds for *serving* data: it keeps upstream
traffic proportional to distinct stale series rather than to request volume.

What it does not give us is **detection**. Surge and flood stage are computed in
`overview_from_db` at read time, which has three consequences that only get worse
as the station count grows:

- **Detection is observer-dependent.** A station can exceed its flood threshold at
  03:00 and nothing registers it until someone loads the dashboard. The background
  sweep refreshes the *data* but never evaluates it.
- **New reactions require editing the ingest path.** Alerting, archiving, or
  writing to a downstream system would each mean another branch inside the cache
  path, which is the one piece of code that must not break.
- **Detection failures become ingest failures.** Because both live in the same call
  stack, a detector that is slow, crashing, or mid-deploy takes data collection
  down with it. For a monitoring system that is precisely backwards: the moment
  detection is broken is the moment you most want the raw data still landing.

The scale we care about is not 13 NOAA stations. It is the shape the system would
need to hold if each station were a spacecraft emitting continuous telemetry, where
ingest must never pause and several independent consumers care about every reading.

## Decision

Publish each newly stored reading as an event to a **RabbitMQ topic exchange**, and
move anomaly evaluation into a **separate consumer process** that persists its
findings.

```
poller ──► exchange (topic) ──┬── reading.water_level ──► anomaly detector
                              └── reading.*            ──► (future consumers)
```

Four supporting rules:

- **The broker is additive, not load-bearing for reads.** If RabbitMQ is
  unavailable, publishing fails soft and the existing read-through cache continues
  to serve exactly as it does today. Degraded means "no new anomaly rows", not
  "no data".
- **Routing keys are `reading.<product>`**, so a future consumer binds a new queue
  to an existing exchange without any publisher change. This is the entire reason
  for publishing to an exchange rather than directly to a queue.
- **Delivery is at-least-once, and consumers must be idempotent.** Messages are
  acknowledged only after the consumer has committed its work, so a consumer that
  dies mid-message will see that message again on restart. Anomaly writes are keyed
  on `(station_id, product, ts)` so a redelivery overwrites rather than duplicates.
- **Messages that cannot ever be processed are dead-lettered** rather than retried
  forever, so one malformed payload cannot stall the queue behind it.

RabbitMQ over Kafka: the workload is modest-volume routing to a handful of
consumers, not a replayable event log with long retention. Kafka's partition and
offset model is real operational weight to carry for a benefit this system does not
currently need. If replay ever becomes a requirement, that is the trigger to
revisit.

## Consequences

- Anomalies are detected **when they happen**, not when someone looks, and the
  detector's uptime is decoupled from the API's.
- The system now has a second process to run and a broker to operate. `make dev`
  and the compose setup have to start both, and "is the consumer alive" becomes a
  thing that can be false while the API looks perfectly healthy — so consumer lag
  and queue depth are exported as metrics (see
  [ADR 0004](0004-in-process-rate-limiting-and-metrics.md)).
- At-least-once delivery means duplicate processing is **normal**, not exceptional.
  Every consumer added later inherits the obligation to be idempotent; that is a
  standing constraint, not a one-off implementation detail.
- Read-time surge computation stays where it is for now. Serving persisted anomaly
  rows instead is a follow-on change, deliberately kept separate so this one can be
  reverted without touching the read path.
