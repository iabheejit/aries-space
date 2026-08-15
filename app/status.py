from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, func, select

from app import config, ingest
from app.models import Observation


def compute_status(session: Session) -> dict:
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    count_24h = session.exec(
        select(func.count()).select_from(Observation).where(
            Observation.ingested_at >= since_24h
        )
    ).one()

    last_ingested_at: Optional[datetime] = session.exec(
        select(func.max(Observation.ingested_at))
    ).one()

    total_observations = session.exec(
        select(func.count()).select_from(Observation)
    ).one()

    return {
        "satellite": {"norad_id": config.NORAD_ID, "name": config.SATELLITE_NAME},
        "station": {
            "name": config.STATION_NAME,
            "lat": config.STATION_LAT,
            "lon": config.STATION_LON,
            "elevation_m": config.STATION_ELEV_M,
        },
        "observations_ingested_last_24h": count_24h,
        "observations_total": total_observations,
        "last_successful_ingestion": (
            last_ingested_at.isoformat() if last_ingested_at else None
        ),
        "last_ingestion_error": ingest.get_last_ingestion_error(),
    }
