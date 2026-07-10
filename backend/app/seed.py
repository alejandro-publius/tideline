"""Curated set of NOAA CO-OPS water-level stations shown on the map.

Coordinates and flood thresholds come from the NOAA station metadata API
(https://api.tidesandcurrents.noaa.gov/mdapi/prod/): flood levels are the
official NWS thresholds when published, falling back to NOAA's derived NOS
values, converted from feet-above-station-datum to meters above MLLW using
each station's datum table. South Beach's "major" level is omitted because
the NWS/NOS source mix there is non-monotonic (major below moderate).
"""

from sqlalchemy.orm import Session

from .models import Station

# (id, name, state, lat, lon, flood_minor, flood_moderate, flood_major) — meters MLLW
SEED_STATIONS: list[
    tuple[str, str, str, float, float, float | None, float | None, float | None]
] = [
    ("9414290", "San Francisco", "CA", 37.806305, -122.46589, 2.146, 2.633, 3.021),
    ("9414750", "Alameda", "CA", 37.771954, -122.30026, 2.591, 2.871, 3.261),
    ("9415020", "Point Reyes", "CA", 37.994167, -122.97361, 2.326, 2.609, 2.996),
    ("9413450", "Monterey", "CA", 36.60889, -121.89139, 2.192, 2.475, 2.862),
    ("9410840", "Santa Monica", "CA", 34.0083, -118.5, 2.143, 2.448, 2.89),
    ("9410230", "La Jolla", "CA", 32.86689, -117.25714, 2.14, 2.472, 2.859),
    ("9447130", "Seattle", "WA", 47.60264, -122.3393, 4.103, 4.377, 4.499),
    ("9435380", "South Beach", "OR", 44.625446, -124.044945, 3.67, 4.432, None),
    ("8443970", "Boston", "MA", 42.35389, -71.05028, 3.81, 4.417, 4.877),
    ("8518750", "The Battery", "NY", 40.700554, -74.01417, 2.195, 2.576, 3.033),
    ("8723214", "Virginia Key", "FL", 25.7314, -80.1618, 1.076, 1.198, 1.442),
    ("8771341", "Galveston Bay Entrance", "TX", 29.357462, -94.724724, 1.061, 1.21, 1.362),
    ("1612340", "Honolulu", "HI", 21.303333, -157.86453, 0.792, 1.396, 1.774),
]


def seed_stations(db: Session) -> None:
    for sid, name, state, lat, lon, minor, moderate, major in SEED_STATIONS:
        station = db.get(Station, sid)
        if station is None:
            db.add(
                Station(
                    id=sid,
                    name=name,
                    state=state,
                    lat=lat,
                    lon=lon,
                    flood_minor=minor,
                    flood_moderate=moderate,
                    flood_major=major,
                )
            )
        else:
            # keep existing rows in sync when seed data gains fields
            station.flood_minor = minor
            station.flood_moderate = moderate
            station.flood_major = major
    db.commit()
