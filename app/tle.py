from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import httpx

from app import config


class TLEUnavailableError(Exception):
    """Raised when no TLE (live or cached) is available for a satellite."""


@dataclass
class TLERecord:
    norad_id: int
    name: str
    line1: str
    line2: str
    fetched_at: datetime
    stale: bool = False


_cache: Dict[int, TLERecord] = {}


def _fetch_live(norad_id: int) -> TLERecord:
    response = httpx.get(
        config.CELESTRAK_URL,
        params={"CATNR": norad_id, "FORMAT": "TLE"},
        timeout=15,
    )
    response.raise_for_status()
    lines = [line.strip() for line in response.text.strip().splitlines() if line.strip()]
    if len(lines) < 3:
        raise TLEUnavailableError(f"Celestrak returned no TLE for NORAD {norad_id}")
    name, line1, line2 = lines[0], lines[1], lines[2]
    return TLERecord(
        norad_id=norad_id,
        name=name,
        line1=line1,
        line2=line2,
        fetched_at=datetime.now(timezone.utc),
        stale=False,
    )


def get_tle(norad_id: int) -> TLERecord:
    """Return a fresh TLE, falling back to the last cached one if Celestrak
    is unreachable. Raises TLEUnavailableError only if there is no live
    fetch AND no cache at all.
    """
    cached = _cache.get(norad_id)
    is_expired = cached is None or (
        datetime.now(timezone.utc) - cached.fetched_at
        > timedelta(hours=config.TLE_REFRESH_HOURS)
    )

    if not is_expired:
        return cached

    try:
        record = _fetch_live(norad_id)
        _cache[norad_id] = record
        return record
    except (httpx.HTTPError, TLEUnavailableError):
        if cached is not None:
            cached.stale = True
            return cached
        raise TLEUnavailableError(
            f"No live TLE reachable and no cached TLE for NORAD {norad_id}"
        )


def reset_cache(norad_id: Optional[int] = None) -> None:
    if norad_id is None:
        _cache.clear()
    else:
        _cache.pop(norad_id, None)
