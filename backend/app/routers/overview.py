from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..noaa import NoaaClient
from ..schemas import OverviewOut, StationOverviewOut
from ..service import get_overview
from .stations import get_noaa_client

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewOut)
def overview(
    db: Session = Depends(get_db),
    client: NoaaClient = Depends(get_noaa_client),
) -> OverviewOut:
    """Latest observed level, prediction, and surge residual for every station.

    Powers the surge-colored map markers. Stations NOAA can't answer for
    come back with null values rather than failing the whole response.
    """
    return OverviewOut(
        stations=[StationOverviewOut.model_validate(row) for row in get_overview(db, client)]
    )
