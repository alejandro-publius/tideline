# Deploying Tideline

Two shapes are supported. The **single-service** deploy is simplest: one Docker
image serves both the API and the built frontend from the same origin. The
**split** deploy hosts the frontend on a static/edge platform and the backend
separately — useful if you want the frontend on a CDN.

> Live URL: `TODO (human):` paste the deployed URL here once it's live.

---

## Option A — Single service on Render (recommended)

The repo ships a [`Dockerfile`](Dockerfile) (multi-stage: Node builds the SPA,
a slim Python image serves the bundle + API from one process) and a
[`render.yaml`](render.yaml) Blueprint.

1. Push this repo to GitHub (already done if you're reading this there).
2. On [Render](https://render.com): **New → Blueprint**, and select the repo.
   `render.yaml` configures the Docker runtime, the free plan, and a health
   check on `/api/healthz`.
3. (Optional but recommended) Set `TIDELINE_DATABASE_URL` to a managed Postgres
   URL so accumulated surge history survives redeploys — the free tier's disk
   is ephemeral. A free [Neon](https://neon.tech) instance works; use a
   `postgresql+psycopg://…` URL. Leave it unset to run on ephemeral SQLite.
4. Deploy. Pushes to `main` auto-deploy thereafter.

Verify:

```bash
curl -sf https://<your-app>.onrender.com/api/healthz     # {"status":"ok"}
open   https://<your-app>.onrender.com/docs               # interactive API docs
open   https://<your-app>.onrender.com/api/metrics        # Prometheus counters
```

### Run the same image locally

```bash
docker build -t tideline .
docker run -p 8000:8000 tideline      # SPA + API at http://localhost:8000
```

---

## Option B — Split deploy (frontend on Vercel/Netlify, backend on Render)

The frontend reads its API base from the `VITE_API_BASE` build-time variable
(defaulting to same-origin), so it can point at a separately-hosted backend.

**Backend** (Render, as in Option A but API-only):
- Deploy the Docker image. Set `TIDELINE_CORS_ORIGINS` to the frontend's origin
  (e.g. `https://tideline.vercel.app`) so the browser is allowed to call it.

**Frontend** (Vercel or Netlify):
- Framework preset: **Vite**. Build command `npm run build`, output `dist`,
  root directory `frontend`.
- Set the env var `VITE_API_BASE=https://<your-backend>.onrender.com`.
- Deploy. The static bundle now calls the backend cross-origin.

---

## Environment variables

Full list with defaults is in [`.env.example`](.env.example). The ones that
usually matter for a deploy:

| Variable | Purpose |
|---|---|
| `TIDELINE_DATABASE_URL` | Postgres URL for durable history; omit for ephemeral SQLite |
| `TIDELINE_CORS_ORIGINS` | Frontend origin(s) allowed to call the API (split deploy) |
| `TIDELINE_STATIC_DIR` | Where to serve the built SPA from (set by the Dockerfile) |
| `TIDELINE_RATE_LIMIT_PER_MINUTE` | Per-client request budget (0 disables) |
| `TIDELINE_HISTORY_REFRESH_MINUTES` | Background sweep that accumulates surge history |

---

## Post-deploy checklist

- [ ] `GET /api/healthz` returns `{"status": "ok"}`
- [ ] `/docs` renders the interactive API
- [ ] The map loads and markers show colors (needs at least one NOAA fetch, or
      seed the database — see below)
- [ ] `TODO (human):` capture a real screenshot/GIF of the live app for the README

### Seeding a demo database

To show the full app without waiting on live NOAA data (or to demo offline):

```bash
python -m app.seed_demo --days 14   # from the backend/ directory
```

This populates realistic synthetic tides and marks the cache fresh, so every
endpoint serves from the database.
