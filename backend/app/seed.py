"""Curated set of NOAA CO-OPS water-level stations shown on the map.

Coordinates come from the NOAA station metadata API
(https://api.tidesandcurrents.noaa.gov/mdapi/prod/).
"""

from sqlalchemy.orm import Session

from .models import Station

SEED_STATIONS: list[tuple[str, str, str, float, float]] = [
    ("9414290", "San Francisco", "CA", 37.806305, -122.46589),
    ("9414750", "Alameda", "CA", 37.771954, -122.30026),
    ("9415020", "Point Reyes", "CA", 37.994167, -122.97361),
    ("9413450", "Monterey", "CA", 36.60889, -121.89139),
    ("9410840", "Santa Monica", "CA", 34.0083, -118.5),
    ("9410230", "La Jolla", "CA", 32.86689, -117.25714),
    ("9447130", "Seattle", "WA", 47.60264, -122.3393),
    ("9435380", "South Beach", "OR", 44.625446, -124.044945),
    ("8443970", "Boston", "MA", 42.35389, -71.05028),
    ("8518750", "The Battery", "NY", 40.700554, -74.01417),
    ("8723214", "Virginia Key", "FL", 25.7314, -80.1618),
    ("8771341", "Galveston Bay Entrance", "TX", 29.357462, -94.724724),
    ("1612340", "Honolulu", "HI", 21.303333, -157.86453),
]


def seed_stations(db: Session) -> None:
    for sid, name, state, lat, lon in SEED_STATIONS:
        if db.get(Station, sid) is None:
            db.add(Station(id=sid, name=name, state=state, lat=lat, lon=lon))
    db.commit()
