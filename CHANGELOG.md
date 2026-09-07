# Changelog

All notable changes to this project are documented in this file, seeded from
`git log`. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-09-07

First tagged release. Dates below are when each piece of work actually
landed on `main`, per `git log`.

### Added

- FastAPI backend that caches NOAA CO-OPS water levels and astronomical tide
  predictions in SQLite (Postgres also supported), with a read-through cache
  and station REST endpoints (2026-07-09)
- React + TypeScript frontend: interactive Leaflet station map, observed-vs-predicted
  chart, dark mode, and responsive app shell (2026-07-10)
- Surge residual mini-chart with a crosshair synced to the main chart, next
  high/low tide countdown, shareable URLs, station dropdown, and 5-minute
  auto-refresh (2026-07-10)
- `GET /api/overview` — latest surge for every station in one call, with
  surge-colored map markers and a legend (2026-07-10)
- NWS flood-stage classification and flood thresholds, shown in the chart,
  stat tiles, and map (2026-07-10)
- Metric/US units toggle (m·°C / ft·°F) and CSV dataset export, both backend
  endpoint and frontend button (2026-07-10 – 2026-07-11)
- NOAA client resilience: exponential-backoff retry on transient failures,
  structured logging, and a short in-process response memo (2026-07-11)
- Rate limiting (token bucket, `429` + `Retry-After`) and Prometheus-format
  metrics at `/api/metrics` (2026-07-11)
- Offline demo seeder (`app.seed_demo`) so the app runs with no NOAA
  connection, plus an end-to-end test, coverage, and mypy configuration
  (2026-07-11)
- GitHub Actions CI (backend lint + type-check + tests against SQLite and
  Postgres, frontend lint + test + build, Docker build and smoke test),
  Dependabot, ADRs, Makefile, DEPLOY.md, WRITEUP.md (2026-07-10 – 2026-07-11)
- MCP server (`backend/app/mcp_server.py`) exposing Tideline's data as agent
  tools — `list_stations`, `surge_overview`, `station_surge`, `surge_history`
  (2026-07-14)
- Accessible focus rings, reduced-motion support, and tactile depth in the UI
  (2026-07-14)
- Event-driven anomaly detection: newly stored readings publish to a RabbitMQ
  topic exchange; a standalone detector process judges them against NWS flood
  thresholds and the astronomical prediction, dead-lettering what it can never
  process; results are served at `GET /api/anomalies` and shown in the
  dashboard's anomaly feed (2026-08-08)
- A stdio round-trip test that pins the MCP server's tool schema (names,
  argument names, `station_id`/`days` shape) against what the README
  documents, plus a test covering the overview endpoint when a station has an
  observed reading but no tide prediction (2026-09-07)
- `CHANGELOG.md` and `.pre-commit-config.yaml` (ruff check + format on the
  backend) (2026-09-07)
- Fresh, real dashboard/dark-mode/mobile screenshots captured against live
  NOAA data, replacing the July ones (2026-09-07)

### Fixed

- NOAA "no data was found" responses treated as an empty series rather than
  an outage; non-JSON NOAA responses (e.g. a maintenance page) treated as an
  outage rather than a crash (2026-07-10)
- Map retiles when its container resizes (2026-07-10)
- Anomaly recording made idempotent under message redelivery (2026-08-08)
- Frontend `postcss` dependency advisories patched (2026-09-06)
- Stale test counts and a missing Python-version badge in the README's top
  screen corrected against a fresh install and test run (2026-09-07)

### Changed

- CI token permissions tightened to least privilege, with superseded runs
  cancelled automatically (2026-09-04)
- Backend cleaned up under ruff 0.16 (2026-08-08)
