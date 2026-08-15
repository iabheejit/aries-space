from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.api.aries_api import config
from services.api.aries_api.models import Observation


def compute_status(session: Session) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    count_24h = session.scalar(
        select(func.count()).select_from(Observation).where(Observation.ingested_at >= since)
    )
    last_ingested_at = session.scalar(select(func.max(Observation.ingested_at)))
    total = session.scalar(select(func.count()).select_from(Observation))
    return {
        "satellite": {"norad_id": config.NORAD_ID, "name": config.SATELLITE_NAME},
        "station": {
            "name": config.STATION_NAME,
            "lat": config.STATION_LAT,
            "lon": config.STATION_LON,
            "elevation_m": config.STATION_ELEV_M,
        },
        "observations_ingested_last_24h": count_24h or 0,
        "observations_total": total or 0,
        "last_successful_ingestion": last_ingested_at.isoformat() if last_ingested_at else None,
        "last_ingestion_error": None,
    }