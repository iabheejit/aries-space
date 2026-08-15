import json
import logging
from datetime import datetime, timezone
from typing import List

import httpx
from sqlmodel import Session, select

from app import config
from app.models import Observation
from app.normalize import normalize_observation

logger = logging.getLogger("missionops.ingest")

_last_successful_ingestion: datetime | None = None
_last_ingestion_error: str | None = None


def get_last_successful_ingestion() -> datetime | None:
    return _last_successful_ingestion


def get_last_ingestion_error() -> str | None:
    return _last_ingestion_error


def fetch_recent_observations(norad_id: int, limit: int = 25) -> List[dict]:
    """Fetch recently-completed ("good") observations — excludes future/
    scheduled passes that have no waterfall/audio/decoded data yet.
    """
    response = httpx.get(
        config.SATNOGS_OBSERVATIONS_URL,
        params={"norad_cat_id": norad_id, "status": "good"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()[:limit]


def ingest_observations(session: Session) -> int:
    """Poll SatNOGS for the configured satellite and store any new
    observations (raw + normalized). Returns the count of newly-stored
    rows. On failure, leaves prior ingestion state untouched and does not
    raise — the scheduler retries on the next interval.
    """
    global _last_successful_ingestion, _last_ingestion_error

    try:
        raw_observations = fetch_recent_observations(config.NORAD_ID)
    except httpx.HTTPError as exc:
        _last_ingestion_error = str(exc)
        logger.warning("SatNOGS poll failed: %s", exc)
        return 0

    stored = 0
    for raw in raw_observations:
        existing = session.exec(
            select(Observation).where(
                Observation.satnogs_observation_id == raw["id"]
            )
        ).first()
        if existing is not None:
            continue

        normalized = normalize_observation(raw)
        observation = Observation(
            raw_json=json.dumps(raw),
            ingested_at=datetime.now(timezone.utc),
            **normalized,
        )
        session.add(observation)
        stored += 1

    session.commit()
    _last_successful_ingestion = datetime.now(timezone.utc)
    _last_ingestion_error = None
    return stored
