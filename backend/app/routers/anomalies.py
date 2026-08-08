from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import AnomaliesOut, AnomalyOut
from ..service import recent_anomalies

router = APIRouter(prefix="/api", tags=["anomalies"])


@router.get("/anomalies", response_model=AnomaliesOut)
def anomalies(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    station_id: str | None = None,
    kind: Literal["flood", "surge"] | None = None,
) -> AnomaliesOut:
    """Anomalies the detector has recorded, newest first.

    Purely a read of what the detector already found (see ADR 0007) — no NOAA
    calls and no recomputation. If the detector is down this returns the last
    thing it knew rather than quietly recalculating, so a stale list is a signal
    that the detector needs looking at.
    """
    return AnomaliesOut(
        anomalies=[
            AnomalyOut.model_validate(row)
            for row in recent_anomalies(db, limit=limit, station_id=station_id, kind=kind)
        ]
    )
