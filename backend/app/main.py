from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .database import Base, SessionLocal, engine
from .seed import seed_stations


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_stations(db)
    yield


app = FastAPI(title="Tideline API", version="0.1.0", lifespan=lifespan)
settings = get_settings()


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
