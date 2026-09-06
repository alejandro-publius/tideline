# Tideline 🌊

**Live NOAA water levels vs. astronomical tide predictions — and the surge residual between them.**

[![CI](https://github.com/alejandro-publius/tideline/actions/workflows/ci.yml/badge.svg)](https://github.com/alejandro-publius/tideline/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/alejandro-publius/tideline/branch/main/graph/badge.svg)](https://codecov.io/gh/alejandro-publius/tideline)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

There is no public instance to link to. Tideline runs locally in two commands (see [Running locally](#running-locally)) and deploys in one click from the `render.yaml` Blueprint (see [DEPLOY.md](DEPLOY.md) and [Deploying](#deploying-to-render-free-tier)); with the bundled demo seed it needs no network at all.

Tideline pulls real-time coastal data from the [NOAA CO-OPS API](https://api.tidesandcurrents.noaa.gov/api/prod/), caches it in SQLite, and shows each station's **observed water level** against the **astronomical prediction** (the tide as pure celestial mechanics would have it). The difference between the two — the **surge residual** — is the interesting part: it's the signature of storm surge, wind setup, and pressure anomalies that the tide tables can't see.

![3D surge globe](docs/screenshots/globe.png)

![Tideline dashboard](docs/screenshots/dashboard.png)

<p align="center">
  <img src="docs/screenshots/dashboard-dark.png" alt="Dark mode" width="49%">
  <img src="docs/screenshots/mobile.png" alt="Mobile layout" width="24%">
</p>

## Features

- **3D surge globe** — the whole coastline as a slowly-turning planet in space: every station is a luminous pillar whose **height and color are its live storm-surge residual**, keyed on an [AlphaFold](https://alphafold.ebi.ac.uk/)-style confidence ramp (calm blue → storm orange). Drag to orbit, ctrl + scroll to zoom (a hero must never hijack page scrolling), click a pillar to dive into that station; stations at flood stage pulse a radar ping. It's lazy-loaded so three.js never touches first paint, pauses itself when scrolled off-screen, honors `prefers-reduced-motion`, and falls back to the 2D map where WebGL is unavailable.
- **National surge overview** — map markers turn red/blue when a station runs beyond ±0.15 m of its predicted tide, so one glance shows which coast is anomalous right now
- **Interactive station map** — 13 NOAA stations across both coasts, Gulf, and Hawaii; click a marker or use the dropdown (the map pans to off-screen picks)
- **Observed vs. predicted overlay chart** with a "now" marker, so you can see the upcoming tide as well as the last few days
- **Surge residual chart** — a diverging mini-chart of observed − predicted with a crosshair synced to the main chart; a rising residual is what a storm looks like
- **Next high/low tide** with a live countdown, derived from the prediction series
- **Shareable URLs** — station, product, and time range round-trip through the query string
- **Read-through cache with graceful degradation** — repeated requests serve from SQLite; if NOAA is unreachable the API returns the last known data flagged `stale`, and the UI offers a retry
- **Resilient NOAA pipeline** — transient upstream failures (network errors, 5xx) retry with exponential backoff; deterministic ones fail fast and degrade to the stale cache instead of hammering a struggling API; after a failure, a short per-series cooldown serves stale data immediately instead of re-paying the retry cost on every request
- **Event-driven anomaly detection** — newly stored readings are published to a RabbitMQ exchange and judged by a separate consumer process, against both the station's NWS flood thresholds and its astronomical tide prediction, so a crossing is recorded when it happens rather than when someone opens the dashboard; the findings are served at `GET /api/anomalies`
- **Rate-limited, observable API** — per-client token bucket (`429` + `Retry-After`, health checks exempt) and Prometheus-format counters at `/api/metrics`: requests by route, cache hit/miss/stale, NOAA outcomes and retries, throttles
- **CSV dataset export** — each station's accumulated observed/predicted/surge history as an analysis-ready download, one click from the dashboard
- Stations without a sensor for a product (SF has no thermometer!) get a friendly empty state, not an error
- **Metric/US units toggle** (m·°C / ft·°F) — data stays metric internally; conversion happens only at the display boundary
- Water temperature as a second data product, 5-minute auto-refresh, responsive layout, automatic dark mode, loading skeletons, split vendor chunks

## Architecture

```mermaid
flowchart LR
    subgraph Browser
        UI[React + TypeScript<br/>three.js surge globe · Leaflet map · Recharts charts]
    end
    subgraph Agents[AI agents]
        CLIENT[MCP client<br/>Claude Desktop · agent platforms]
    end
    subgraph Backend[FastAPI]
        API[REST API]
        MCPS[MCP server<br/>stdio · read-only tools]
        SVC[Cache service<br/>TTL + stale fallback + failure cooldown]
        SCHED[Scheduler<br/>periodic surge-history sweep]
    end
    MQ{{RabbitMQ topic exchange<br/>tideline.readings}}
    DET[Detector process<br/>flood thresholds · surge residual]
    DB[(SQLite / Postgres<br/>stations · readings · anomalies · fetch log)]
    NOAA[NOAA CO-OPS API]

    UI -- "/api/*" --> API
    CLIENT -- "tool calls" --> MCPS
    API --> SVC
    MCPS -- "shared read path" --> SVC
    SCHED -- "background ingest" --> SVC
    SVC <--> DB
    SVC -- "on cache miss / refresh" --> NOAA
    SVC -- "publish new readings" --> MQ
    MQ -- "bind reading.* · queue anomaly.detector" --> DET
    DET -- "anomalies" --> DB
```

The cache is the heart of the backend (`backend/app/service.py`):

1. Every `(station, product)` pair has a **fetch log** entry recording when it was last refreshed from NOAA (TTL: 10 min for observations, 12 h for predictions — astronomy doesn't change often).
2. On a cache miss, the service **always fetches the full 72-hour window**, not just the requested range — otherwise a narrow request could mark a wide range as "fresh" while the database only holds a sliver of it.
3. Readings are **upserted**, so history accumulates across pulls and re-fetches never duplicate rows.
4. If NOAA errors or times out, previously cached data is served with `source: "stale"` — the dashboard stays useful through an upstream outage and says so in the header badge.

All timestamps are stored as naive UTC and serialized with an explicit `Z` suffix; the frontend renders them in the viewer's local time.

### The event path

Serving data and judging it are different jobs with different failure modes, so they run as different processes. Every genuinely new reading the cache stores is published — after the commit, never before — to a durable RabbitMQ topic exchange (`tideline.readings`) under the routing key `reading.<product>`. A consumer process (`backend/app/detector.py`) binds the queue `anomaly.detector` to `reading.*` and evaluates each water-level reading two ways:

- **Flood** — the absolute level against that station's published NWS minor/moderate/major thresholds.
- **Surge** — the residual against the astronomical prediction for the *same* timestamp, which catches what an absolute threshold cannot: 1.4 m is unremarkable at high tide and alarming at low tide. Anything beyond ±`TIDELINE_SURGE_THRESHOLD_M` (default 0.15 m) is recorded; a timestamp with no prediction yields no verdict, since a missing prediction is an absence of evidence rather than evidence of calm.

Findings persist to an `anomalies` table and are served at `GET /api/anomalies`. That endpoint is a plain read of what the detector already wrote — no NOAA call, no recomputation — so if the detector is down the list goes stale and visibly says so, rather than quietly recalculating and hiding the fact.

Three properties fall out of running detection off a queue:

1. **Detection stops being observer-dependent.** A station that crosses its flood stage at 03:00 is recorded at 03:00, not the next time someone loads the dashboard. Adding a second reaction later — alerting, archiving — is a new queue bound to the existing exchange, not another branch inside the ingest path.
2. **Publishing fails soft.** A publish to an unreachable broker is logged and counted, never raised: the API keeps serving reads exactly as before, and the degradation is "no new anomaly rows", not "no data". Setting `TIDELINE_BROKER_URL` to empty disables publishing entirely, which is how the tests and a broker-less local run work.
3. **Delivery is at-least-once, so duplicate processing is normal rather than exceptional.** A message is acknowledged only once its work is committed, which means a consumer that dies mid-message sees that message again on restart. Anomaly rows are keyed on `(station_id, product, ts, kind)` and writes skip what is already recorded, so a redelivery is a no-op instead of a second row. Messages that can never succeed — a malformed payload — are dead-lettered to `anomaly.detector.dead` rather than retried forever in front of everything queued behind them.

The decisions behind this shape — cache vs. scheduled ingestion, SQLite-first, the retry policy, in-process rate limiting, [RabbitMQ rather than Kafka](docs/adr/0007-event-driven-anomaly-detection.md) — are written up as [architecture decision records](docs/adr/).

## Engineering challenges

The interesting problems, in brief; the full narrative is in [WRITEUP.md](WRITEUP.md).

- **Reconciling predictions against observations.** Observed levels and astronomical predictions are two independent NOAA products; their difference is only meaningful when both are sampled at the *same* instant, so readings are stored on NOAA's native 6-minute grid and paired by exact timestamp.
- **Computing the surge residual.** `observed − predicted` is the entire non-astronomical signal — storm surge, wind setup, pressure anomalies. It's aggregated per UTC day for the history view and exposed row-by-row via CSV export.
- **Missing and late readings.** Sensor gaps arrive as empty values, maintenance windows as non-JSON `200`s, and some stations lack a sensor entirely — all treated as *absence*, never as zero and never as a crash.
- **Time-series storage and accumulation.** Refreshes upsert over the full 72-hour window, so history accumulates without duplicate rows; a background sweep keeps it growing with no visitors, which is what makes daily-surge history and export possible without a separate ingestion pipeline.
- **NWS flood-stage mapping.** Observed levels are classified against each station's official minor/moderate/major thresholds (meters above MLLW), so the map shows not just "anomalous" but "anomalous relative to what floods *here*."
- **Detecting anomalies without putting detection on the ingest path.** Evaluating readings inline would mean a slow or crashing detector takes data collection down with it, which is backwards for a monitoring system: the moment detection breaks is the moment you most want the raw data still landing. Readings are handed to a broker instead and judged in a separate process, which makes at-least-once redelivery — and therefore idempotent writes — a design constraint rather than an afterthought.
- **NOAA rate limiting and flakiness.** The read-through cache collapses repeated requests; transient failures retry with exponential backoff while deterministic ones fail fast; an in-process memo de-duplicates identical calls, and a per-series failure cooldown serves stale data during an outage instead of re-paying the retry cost per request — together keeping load on NOAA low and the app responsive when NOAA isn't.

## Security & operations

- **Rate limiting** (`backend/app/ratelimit.py`): a token bucket per client IP — burst up to 120 requests, refilled continuously — returns `429` with `Retry-After` beyond the budget. `/api/healthz` is exempt so a throttled client can't make the platform health check report the service down, and the bucket map is pruned so address-cycling can't grow it without bound.
- **Metrics** (`backend/app/metrics.py`): counters exposed at `/api/metrics` in Prometheus text format. Request labels use the matched route *template*, not the raw URL, so path parameters and scanner probes can't mint unbounded label values. Publish outcomes are counted too (`tideline_readings_published_total`, labelled `ok`/`failed`), so a broker that has quietly gone away shows up as a rising failure count rather than as silence.
- **Structured logs**: retries, stale fallbacks, and background sweeps are logged as key=value events.
- **Contained blast radius elsewhere**: CORS allows `GET` only, the Docker image runs as a non-root user, and Dependabot keeps all four ecosystems (pip, npm, Actions, Docker) patched weekly with CI as the merge gate.

## API

Interactive docs at `/docs` (Swagger UI, generated by FastAPI).

| Endpoint | Description |
|---|---|
| `GET /api/stations` | All stations with coordinates |
| `GET /api/overview` | Latest observed level, prediction, and surge for every station (powers the map colors); stale stations refresh from NOAA in parallel threads |
| `GET /api/stations/{id}/readings?product=water_level&hours=24` | Observed readings for the trailing window (1–72 h); `product` may also be `water_temperature` |
| `GET /api/stations/{id}/predictions?hours=24` | Astronomical tide predictions from `hours` ago (1–72 h) to up to 48 h ahead |
| `GET /api/stations/{id}/history?days=30` | Daily surge statistics (avg/max/samples) from accumulated history — served entirely from the database (1–365 d) |
| `GET /api/stations/{id}/export?days=30` | Accumulated observed/predicted/surge history as a CSV download (1–365 d) |
| `GET /api/anomalies?limit=50` | Anomalies the detector recorded, newest first (1–500); optional `station_id` and `kind` (`flood` / `surge`) filters |
| `GET /api/metrics` | Operational counters, Prometheus text format |
| `GET /api/healthz` | Health check (never rate-limited) |

Series responses include `source` (`noaa` / `cache` / `stale`) and `fetched_at`, so clients can tell exactly how fresh the data is.

## MCP server — Tideline as a tool for AI agents

The same data is exposed over the [Model Context Protocol](https://modelcontextprotocol.io) (`backend/app/mcp_server.py`), so an AI assistant can query live surge data directly — ask *"which US coast is running most above its predicted tide right now?"* and get a structured answer, with no knowledge of NOAA, SQL, or this app's HTTP API.

```bash
cd backend && python -m app.mcp_server      # serves over stdio (or: make mcp)
```

| Tool | Returns |
|---|---|
| `list_stations()` | Every station with location and NWS flood thresholds (minor/moderate/major) |
| `surge_overview()` | Latest surge for all stations, **most anomalous first** |
| `station_surge(station_id)` | Latest observed / predicted / surge / flood stage for one station |
| `surge_history(station_id, days=30)` | Daily surge statistics over the trailing window |

The tools reuse the exact same read-only query functions as the REST API (`service.overview_from_db`, `service.daily_surge`), so the two surfaces can't drift apart; every tool reads only the database, so responses are fast and deterministic. Point any MCP client (Claude Desktop, or an agent platform) at the command above to give it eyes on the coast.

## Tech stack

| Layer | Choices |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, httpx, pydantic-settings |
| Database | SQLite (swap to Postgres by changing `TIDELINE_DATABASE_URL` — no dialect-specific SQL) |
| Event path | RabbitMQ (durable topic exchange, dead-letter queue) via `pika`; the detector is a standalone process |
| Frontend | React 19, TypeScript, Vite, react-leaflet, Recharts, three.js (WebGL surge globe) |
| Agent interface | Model Context Protocol server (`mcp`), stdio transport |
| Tests | pytest + respx (NOAA mocked at the HTTP transport layer); Vitest for frontend logic |
| CI/CD | GitHub Actions → Docker → Render; Dependabot for dependency updates |
| Tooling | Makefile dev shortcuts, ruff, oxlint, [ADRs](docs/adr/) for design decisions |

## Running locally

Backend (Python ≥ 3.11):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload        # http://127.0.0.1:8000
```

Frontend (Node ≥ 20), in a second terminal:

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173, proxies /api to the backend
```

After the one-time setup, `make backend` / `make frontend` start either server and `make help` lists the rest (tests, lint, format).

### Anomaly detector (optional)

The API runs perfectly well on its own: with `TIDELINE_BROKER_URL` unset, publishing is disabled and nothing about the two commands above changes. To run the event path as well, you need a broker and a third terminal.

```bash
brew install rabbitmq && brew services start rabbitmq
```

That gives you AMQP on `localhost:5672` and the management UI on [localhost:15672](http://localhost:15672) (`guest` / `guest`), where the `tideline.readings` exchange, the `anomaly.detector` queue, and its message rate are all visible. Then point both processes at it — the API is the publisher, so it needs the variable too:

```bash
export TIDELINE_BROKER_URL=amqp://guest:guest@localhost:5672/
cd backend && python -m app.detector      # or: make detector
```

`make dev-broker` starts the API and the detector together with that URL already set. Either can start first — each declares its half of the topology (the publisher the exchange, the detector its queues) and declaring is idempotent — with one caveat: a topic exchange discards messages no queue is bound to, so readings published before the detector has *ever* run are gone. Once the queue exists it is durable, and it buffers while the detector is restarting. The detector exits immediately if `TIDELINE_BROKER_URL` is empty, since there would be nothing to consume.

Only readings the cache newly stores are published, so anomalies appear after a live NOAA fetch — a cache miss from the dashboard, or the background history sweep. The demo seed below writes rows straight to the database rather than through the cache, so it doesn't publish anything and won't produce any.

### Demo data (no NOAA needed)

To explore the full app offline — map colors, surge history, CSV export — seed realistic synthetic tides (semidiurnal + diurnal predictions, plus an observed level with a storm-surge residual):

```bash
cd backend && python -m app.seed_demo --days 14
```

This populates the database and marks the cache fresh, so every endpoint serves without a live NOAA connection — handy for a reviewer or a screenshot. The seeded freshness lasts one cache TTL (10 minutes for observations by default); to stay offline longer, start the server with the TTLs raised, e.g. `TIDELINE_CACHE_TTL_MINUTES=1440 TIDELINE_PREDICTIONS_TTL_MINUTES=1440 TIDELINE_HISTORY_REFRESH_MINUTES=0`.

### Tests

```bash
cd backend && pytest -v      # 101 tests (or: make test-backend)
cd frontend && npm test      # 54 tests (or: make test-frontend)
```

The backend suite covers the full cache lifecycle (cold → warm → expired → stale fallback), the full-window refresh invariant, upsert de-duplication, NOAA response parsing (sensor gaps, no-sensor stations, non-JSON maintenance pages), the retry policy (transient vs. deterministic failures, backoff timing with an injected sleeper), the failure cooldown (an outage is absorbed once, not re-paid per request), write-path idempotency under concurrent refreshes (the losing side of an insert race retries instead of erroring), the predictions look-ahead coverage invariant, rate limiting (bucket math against a fake clock, `429`/`Retry-After` behavior, health-check exemption, bucket pruning), metrics (route-template labels, cardinality bounds), CSV export, flood-stage classification, the overview sweep (including one-station-failure resilience), history aggregation, gzip, and request validation — NOAA is mocked with `respx`, so everything runs offline in a few seconds. The event path is covered without a broker: routing-key construction and the fail-soft publish are tested against a stubbed connection, and the detector's verdicts, redelivery idempotence (including a reading that raises both a flood and a surge verdict, and one that has already recorded half of them), and dead-lettering decisions are tested by calling the message handler directly. In CI the same suite also runs against a real `postgres:16`. The frontend suite covers the tide math (series merging, surge residual, next-extreme detection, axis ticks, unit conversion), URL state round-tripping, signed-level formatting, and the globe helpers (lat/lng→sphere projection, the AlphaFold confidence color ramp, and surge→pillar-height mapping).

## Docker

```bash
docker build -t tideline .
docker run -p 8000:8000 tideline     # SPA + API on http://localhost:8000
```

The image is multi-stage: Node builds the frontend, then a slim Python image serves the static bundle and the API from a single process — no reverse proxy needed.

## Deploying to Render (free tier)

1. Fork/push this repo to GitHub.
2. On [Render](https://render.com): **New → Blueprint**, select the repo — `render.yaml` configures everything (Docker runtime, health check on `/api/healthz`).
3. That's it. Pushes to `main` auto-deploy.

Note: the free tier has an ephemeral disk, so cached history resets on redeploys — the app simply re-fetches from NOAA. Attach a persistent disk mounted at `/data` (or point `TIDELINE_DATABASE_URL` at a managed Postgres) to keep history.

## Configuration

All settings are environment variables with sensible defaults (`backend/app/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `TIDELINE_DATABASE_URL` | `sqlite:///./tideline.db` | SQLAlchemy database URL |
| `TIDELINE_CACHE_TTL_MINUTES` | `10` | Freshness window for observations |
| `TIDELINE_PREDICTIONS_TTL_MINUTES` | `720` | Freshness window for tide predictions |
| `TIDELINE_HISTORY_REFRESH_MINUTES` | `30` | Background sweep interval that keeps surge history accumulating without visitors (`0` disables) |
| `TIDELINE_RATE_LIMIT_PER_MINUTE` | `120` | Per-client API request budget, token bucket (`0` disables limiting) |
| `TIDELINE_NOAA_MAX_RETRIES` | `3` | Retry budget for transient NOAA failures (network errors, 5xx) |
| `TIDELINE_NOAA_BACKOFF_BASE` | `0.5` | Exponential backoff base between retries, in seconds |
| `TIDELINE_NOAA_CACHE_TTL_SECONDS` | `60` | In-process memo TTL for identical NOAA requests |
| `TIDELINE_NOAA_FAILURE_COOLDOWN_SECONDS` | `60` | After a NOAA failure, serve stale for this long instead of retrying per request (`0` disables) |
| `TIDELINE_BROKER_URL` | *(empty)* | AMQP URL for the event path, e.g. `amqp://guest:guest@localhost:5672/`. Empty disables publishing entirely and the detector refuses to start |
| `TIDELINE_BROKER_EXCHANGE` | `tideline.readings` | Durable topic exchange readings are published to |
| `TIDELINE_BROKER_DEAD_LETTER_EXCHANGE` | `tideline.readings.dlx` | Where the detector sends messages it can never process |
| `TIDELINE_BROKER_PUBLISH_TIMEOUT_SECONDS` | `2.0` | How long a publish may block before giving up and carrying on serving reads |
| `TIDELINE_SURGE_THRESHOLD_M` | `0.15` | How far an observation may sit from its prediction before the detector calls it surge, in metres |
| `TIDELINE_LOG_LEVEL` | `INFO` | Logging verbosity |
| `TIDELINE_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins (empty = CORS off) |
| `TIDELINE_STATIC_DIR` | *(empty)* | If set, serve the built frontend from this directory |
| `TIDELINE_NOAA_BASE_URL` | NOAA CO-OPS prod URL | Upstream data API (overridable for testing) |

## License

[MIT](LICENSE)
