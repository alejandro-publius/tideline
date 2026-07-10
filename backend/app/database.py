from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        # check_same_thread=False lets FastAPI's threadpool share the connection pool
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(database_url, pool_pre_ping=True)


def ensure_schema(engine: Engine) -> None:
    """Additive mini-migration: add columns that create_all won't add to
    pre-existing tables. Nullable-column ADDs are safe on SQLite and Postgres.
    """
    columns = {c["name"] for c in inspect(engine).get_columns("stations")}
    missing = [
        name for name in ("flood_minor", "flood_moderate", "flood_major") if name not in columns
    ]
    if not missing:
        return
    with engine.begin() as conn:
        for name in missing:
            conn.execute(text(f"ALTER TABLE stations ADD COLUMN {name} FLOAT"))


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
