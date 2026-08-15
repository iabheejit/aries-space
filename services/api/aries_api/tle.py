import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from services.api.aries_api import config

logger = logging.getLogger("aries.tle")


class TLEUnavailableError(Exception):
    pass


@dataclass
class TLERecord:
    norad_id: int
    name: str
    line1: str
    line2: str
    fetched_at: datetime
    stale: bool = False


_cache: dict[int, TLERecord] = {}


def _fetch_live(norad_id: int) -> TLERecord:
    response = httpx.get(
        config.CELESTRAK_URL,
        params={"CATNR": norad_id, "FORMAT": "TLE"},
        timeout=15,
    )
    response.raise_for_status()
    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    if len(lines) < 3:
        raise TLEUnavailableError(f"Celestrak returned no TLE for NORAD {norad_id}")
    return TLERecord(norad_id, lines[0], lines[1], lines[2], datetime.now(timezone.utc))


def get_tle(norad_id: int) -> TLERecord:
    cached = _cache.get(norad_id)
    expired = cached is None or datetime.now(timezone.utc) - cached.fetched_at > timedelta(
        hours=config.TLE_REFRESH_HOURS
    )
    if not expired:
        return cached
    try:
        record = _fetch_live(norad_id)
        _cache[norad_id] = record
        return record
    except (httpx.HTTPError, TLEUnavailableError):
        if cached is not None:
            cached.stale = True
            logger.warning("Using stale cached TLE for NORAD %d", norad_id)
            return cached
        raise TLEUnavailableError(
            f"No live TLE reachable and no cached TLE for NORAD {norad_id}"
        )


def reset_cache(norad_id: int | None = None) -> None:
    if norad_id is None:
        _cache.clear()
    else:
        _cache.pop(norad_id, None)