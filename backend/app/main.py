import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Base, SessionLocal, engine, ensure_schema
from .logging_config import configure_logging
from .noaa import make_noaa_client
from .routers import overview, stations
from .seed import seed_stations
from .service import get_overview

configure_logging(get_settings().log_level)
logger = logging.getLogger("tideline")


def _refresh_all_stations() -> None:
    """One sweep of every station so surge history accumulates without visitors."""
    settings = get_settings()
    with SessionLocal() as db:
        rows = get_overview(db, make_noaa_client(settings))
    fresh = sum(1 for row in rows if row.observed is not None)
    logger.info("history sweep complete", extra={"stations": len(rows), "with_observation": fresh})


async def _history_loop(interval_minutes: int) -> None:
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await asyncio.to_thread(_refresh_all_stations)
        except Exception:  # never let one bad sweep kill the loop
            logger.exception("background history refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    ensure_schema(engine)
    with SessionLocal() as db:
        seed_stations(db)
    interval = get_settings().history_refresh_minutes
    task = asyncio.create_task(_history_loop(interval)) if interval > 0 else None
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Tideline API", version="0.1.0", lifespan=lifespan)
settings = get_settings()

# Series payloads are a few hundred rows of JSON — well worth compressing
app.add_middleware(GZipMiddleware, minimum_size=1024)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_methods=["GET"],
        allow_headers=["*"],
    )

app.include_router(stations.router)
app.include_router(overview.router)


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# In production the built frontend is served from the same process (see Dockerfile).
static_dir = Path(settings.static_dir) if settings.static_dir else None
if static_dir and static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
