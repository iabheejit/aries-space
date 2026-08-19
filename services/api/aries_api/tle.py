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
_group_cache: dict[str, list[TLERecord]] = {}


def _parse_tle_text(text: str, fetched_at: datetime) -> list[TLERecord]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    records: list[TLERecord] = []
    for index in range(0, len(lines) - 2, 3):
        name, line1, line2 = lines[index].strip(), lines[index + 1], lines[index + 2]
        if not line1.startswith("1 ") or not line2.startswith("2 "):
            continue
        try:
            norad_id = int(line1[2:7])
        except ValueError:
            continue
        records.append(TLERecord(norad_id, name, line1, line2, fetched_at))
    return records


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


def get_group_tles(group: str) -> list[TLERecord]:
    """Fetch every TLE in a Celestrak group, falling back to a stale cache."""
    cached = _group_cache.get(group)
    expired = cached is None or datetime.now(timezone.utc) - cached[0].fetched_at > timedelta(
        hours=config.TLE_REFRESH_HOURS
    )
    if not expired:
        return cached
    try:
        response = httpx.get(
            config.CELESTRAK_URL,
            params={"GROUP": group, "FORMAT": "TLE"},
            timeout=config.TLE_GROUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        records = _parse_tle_text(response.text, datetime.now(timezone.utc))
        if not records:
            raise TLEUnavailableError(f"Celestrak returned no TLEs for group {group}")
        _group_cache[group] = records
        return records
    except (httpx.HTTPError, TLEUnavailableError):
        if cached:
            for record in cached:
                record.stale = True
            logger.warning("Using stale cached TLE group %s", group)
            return cached
        raise TLEUnavailableError(
            f"No live TLE reachable and no cached TLE for group {group}"
        )


def reset_cache(norad_id: int | None = None) -> None:
    if norad_id is None:
        _cache.clear()
        _group_cache.clear()
    else:
        _cache.pop(norad_id, None)