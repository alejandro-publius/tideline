"""Model Context Protocol (MCP) server exposing Tideline's data as agent tools.

MCP is the open protocol that lets an AI assistant call external tools. This
server turns Tideline into one of those tools: an agent can ask "which US coast
is running most above its predicted tide right now?" and get a structured
answer, without knowing anything about NOAA, SQL, or this app's HTTP API.

It reuses the exact same read-only query functions the REST API uses
(`service.overview_from_db`, `service.daily_surge`), so the two surfaces can
never drift apart. Every tool reads only the database — no NOAA calls — so
responses are fast and deterministic; the HTTP layer and background sweep keep
the data fresh.

Run it over stdio (how MCP clients like Claude Desktop or Cohere North launch
a server):

    python -m app.mcp_server

Each tool below returns plain JSON-serializable dicts; the `_*` helpers hold the
logic and are unit-tested directly against a database session.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Station
from .service import daily_surge, overview_from_db

mcp = FastMCP(
    "tideline",
    instructions=(
        "Tools for real coastal water levels and storm surge from NOAA tide "
        "stations. 'Surge' is the observed water level minus the astronomical "
        "tide prediction — the storm-and-wind signal the tide tables can't see. "
        "A positive surge means water is running higher than predicted."
    ),
)


def _iso(ts: Any) -> str | None:
    return ts.isoformat() + "Z" if ts is not None else None


def _list_stations(db: Session) -> list[dict[str, Any]]:
    stations = db.scalars(select(Station).order_by(Station.name))
    return [
        {
            "id": s.id,
            "name": s.name,
            "state": s.state,
            "lat": s.lat,
            "lon": s.lon,
            "flood_minor_m": s.flood_minor,
        }
        for s in stations
    ]


def _surge_overview(db: Session) -> list[dict[str, Any]]:
    rows = overview_from_db(db)
    out: list[dict[str, Any]] = [
        {
            "station_id": r.station.id,
            "name": r.station.name,
            "state": r.station.state,
            "as_of": _iso(r.ts),
            "observed_m": r.observed,
            "predicted_m": r.predicted,
            "surge_m": r.surge,
            "flood_stage": r.flood_stage,
        }
        for r in rows
    ]
    # Surface the most anomalous stations first — that's what an agent asking
    # "where is the water unusual right now?" actually wants. Stations with no
    # recent reading (surge is None) sort last.
    out.sort(key=lambda r: abs(r["surge_m"]) if r["surge_m"] is not None else -1, reverse=True)
    return out


def _station_surge(db: Session, station_id: str) -> dict[str, Any]:
    station = db.get(Station, station_id)
    if station is None:
        raise ValueError(f"Unknown station {station_id!r}. Call list_stations for valid ids.")
    match = next((r for r in overview_from_db(db) if r.station.id == station_id), None)
    if match is None or match.observed is None:
        return {"station_id": station_id, "name": station.name, "available": False}
    return {
        "station_id": station_id,
        "name": station.name,
        "state": station.state,
        "as_of": _iso(match.ts),
        "observed_m": match.observed,
        "predicted_m": match.predicted,
        "surge_m": match.surge,
        "flood_stage": match.flood_stage,
        "available": True,
    }


def _surge_history(db: Session, station_id: str, days: int) -> dict[str, Any]:
    station = db.get(Station, station_id)
    if station is None:
        raise ValueError(f"Unknown station {station_id!r}. Call list_stations for valid ids.")
    days = max(1, min(days, 365))
    history = daily_surge(db, station_id, days)
    return {
        "station_id": station_id,
        "name": station.name,
        "days": days,
        "daily": [
            {
                "day": d.day.isoformat(),
                "avg_surge_m": d.avg_surge,
                "max_surge_m": d.max_surge,
                "samples": d.samples,
            }
            for d in history
        ],
    }


@mcp.tool()
def list_stations() -> list[dict[str, Any]]:
    """List every monitored NOAA tide station with its location and flood threshold."""
    with SessionLocal() as db:
        return _list_stations(db)


@mcp.tool()
def surge_overview() -> list[dict[str, Any]]:
    """Latest observed level, predicted tide, and surge for every station,
    most anomalous first. Use this to find where water is unusual right now."""
    with SessionLocal() as db:
        return _surge_overview(db)


@mcp.tool()
def station_surge(station_id: str) -> dict[str, Any]:
    """Latest observed level, predicted tide, surge, and flood stage for one
    station (by NOAA id, e.g. '9414290' for San Francisco)."""
    with SessionLocal() as db:
        return _station_surge(db, station_id)


@mcp.tool()
def surge_history(station_id: str, days: int = 30) -> dict[str, Any]:
    """Daily surge statistics (average, max, sample count) for a station over
    the trailing `days` window (1-365), from accumulated history."""
    with SessionLocal() as db:
        return _surge_history(db, station_id, days)


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
