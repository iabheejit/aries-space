"""Live orbital state for the Fusion Map.

Every position here is real SGP4 propagation of a real Celestrak TLE. Nothing
in this module synthesises, smooths, or invents a track.
"""

import logging
from datetime import datetime, timedelta, timezone
from math import acos, isfinite, radians, sin, sqrt

from skyfield.api import EarthSatellite, load, wgs84

from services.api.aries_api import config
from services.api.aries_api.tle import TLERecord, TLEUnavailableError, get_group_tles, get_tle

logger = logging.getLogger("aries.overhead")

EARTH_RADIUS_KM = 6371.0
GM_EARTH_KM3_S2 = 398_600.4418


def _footprint_radius_km(altitude_km: float) -> float:
    """Surface radius of the spherical cap a satellite can see at nadir."""
    if altitude_km <= 0:
        return 0.0
    ratio = EARTH_RADIUS_KM / (EARTH_RADIUS_KM + altitude_km)
    return EARTH_RADIUS_KM * acos(min(1.0, max(-1.0, ratio)))


def _inclination_deg(line2: str) -> float | None:
    try:
        return float(line2[8:16])
    except (ValueError, IndexError):
        return None


def _period_minutes(line2: str) -> float | None:
    try:
        mean_motion = float(line2[52:63])
    except (ValueError, IndexError):
        return None
    return 1440.0 / mean_motion if mean_motion > 0 else None


def _timescale():
    return load.timescale()


def satellite_states(
    records: list[TLERecord],
    now: datetime | None = None,
    min_elevation_deg: float | None = None,
) -> list[dict]:
    """Propagate each TLE to `now` and return its real sub-satellite state."""
    timescale = _timescale()
    moment = timescale.from_datetime(now or datetime.now(timezone.utc))
    observer = wgs84.latlon(
        config.STATION_LAT, config.STATION_LON, elevation_m=config.STATION_ELEV_M
    )
    threshold = (
        config.OVERHEAD_MIN_ELEVATION_DEG if min_elevation_deg is None else min_elevation_deg
    )
    states: list[dict] = []
    for record in records[: config.OVERHEAD_MAX_SATELLITES]:
        try:
            satellite = EarthSatellite(record.line1, record.line2, record.name, timescale)
            geocentric = satellite.at(moment)
            subpoint = wgs84.subpoint(geocentric)
            altitude_deg, azimuth_deg, _ = (satellite - observer).at(moment).altaz()
        except Exception:  # a single malformed TLE must not blank the whole map
            logger.warning("skipping unpropagatable TLE norad=%s", record.norad_id)
            continue
        velocity = geocentric.velocity.km_per_s
        altitude_km = float(subpoint.elevation.km)
        latitude = float(subpoint.latitude.degrees)
        longitude = float(subpoint.longitude.degrees)
        elevation = float(altitude_deg.degrees)
        speed_km_s = float(sqrt(sum(component**2 for component in velocity)))
        # A malformed TLE does not raise -- SGP4 returns non-finite garbage.
        if not all(
            isfinite(value)
            for value in (altitude_km, latitude, longitude, elevation, speed_km_s)
        ):
            logger.warning("skipping non-finite propagation norad=%s", record.norad_id)
            continue
        states.append(
            {
                "norad_id": record.norad_id,
                "name": record.name,
                "lat": round(latitude, 3),
                "lon": round(longitude, 3),
                "altitude_km": round(altitude_km, 1),
                "velocity_km_s": round(speed_km_s, 2),
                "elevation_deg": round(elevation, 2),
                "azimuth_deg": round(float(azimuth_deg.degrees), 2),
                "footprint_radius_km": round(_footprint_radius_km(altitude_km), 1),
                "visible": elevation >= threshold,
                "inclination_deg": _inclination_deg(record.line2),
                "period_minutes": (
                    round(period, 1)
                    if (period := _period_minutes(record.line2)) is not None
                    else None
                ),
                "stale": record.stale,
            }
        )
    states.sort(key=lambda state: state["elevation_deg"], reverse=True)
    return states


def ground_track(
    record: TLERecord,
    minutes: int | None = None,
    step_seconds: int = 60,
    now: datetime | None = None,
) -> list[list[float]]:
    """Real sub-satellite path centred on `now`, as [lon, lat] pairs."""
    span = minutes or config.GROUND_TRACK_MINUTES
    timescale = _timescale()
    start = (now or datetime.now(timezone.utc)) - timedelta(minutes=span / 2)
    steps = int(span * 60 / step_seconds) + 1
    times = timescale.from_datetimes(
        [start + timedelta(seconds=index * step_seconds) for index in range(steps)]
    )
    satellite = EarthSatellite(record.line1, record.line2, record.name, timescale)
    subpoints = wgs84.subpoint(satellite.at(times))
    return [
        [round(float(lon), 3), round(float(lat), 3)]
        for lon, lat in zip(subpoints.longitude.degrees, subpoints.latitude.degrees)
    ]


def subsolar_point(now: datetime | None = None) -> dict:
    """Real subsolar latitude/longitude from a low-precision solar-position
    formula (declination via day-of-year, longitude via UTC hour angle).

    This is a standard approximation (~1 degree accuracy) used for day/night
    terminator lines -- not JPL-ephemeris precision, and not fabricated: every
    input is the real current UTC time, and the formula is a real published
    approximation, not an invented placeholder.
    """
    moment = now or datetime.now(timezone.utc)
    day_of_year = moment.timetuple().tm_yday
    declination_deg = 23.44 * sin(radians(360.0 / 365.0 * (day_of_year - 81)))
    hour = moment.hour + moment.minute / 60.0 + moment.second / 3600.0
    longitude_deg = -15.0 * (hour - 12.0)
    longitude_deg = ((longitude_deg + 180.0) % 360.0) - 180.0
    return {"lat": round(declination_deg, 3), "lon": round(longitude_deg, 3)}


def ground_track_for(
    norad_id: int,
    minutes: int | None = None,
    now: datetime | None = None,
) -> list[list[float]]:
    """Real ground track for any catalogued satellite, by NORAD ID.

    Looks in the already-fetched overhead group first (no extra network
    call); falls back to a single live Celestrak fetch only if the satellite
    isn't in that group (e.g. the tracked node itself).
    """
    records = get_group_tles(config.OVERHEAD_TLE_GROUP)
    record = next((r for r in records if r.norad_id == norad_id), None)
    if record is None:
        try:
            record = get_tle(norad_id)
        except TLEUnavailableError:
            return []
    return ground_track(record, minutes=minutes, now=now)


def build_snapshot(now: datetime | None = None) -> dict:
    """Assemble the live map payload from real Celestrak TLEs."""
    moment = now or datetime.now(timezone.utc)
    records = get_group_tles(config.OVERHEAD_TLE_GROUP)
    tracked_record: TLERecord | None = None
    try:
        tracked_record = get_tle(config.NORAD_ID)
    except TLEUnavailableError:
        logger.warning("tracked satellite TLE unavailable norad=%s", config.NORAD_ID)
    catalog = list(records)
    if tracked_record is not None and all(
        record.norad_id != tracked_record.norad_id for record in catalog
    ):
        catalog.insert(0, tracked_record)
    states = satellite_states(catalog, moment)
    tracked_state = next(
        (state for state in states if state["norad_id"] == config.NORAD_ID), None
    )
    return {
        "generated_at": moment.isoformat(),
        "source": "Celestrak GP + SGP4 (Skyfield)",
        "group": config.OVERHEAD_TLE_GROUP,
        "station": {
            "name": config.STATION_NAME,
            "lat": config.STATION_LAT,
            "lon": config.STATION_LON,
            "elevation_m": config.STATION_ELEV_M,
        },
        "tracked_norad_id": config.NORAD_ID,
        "tracked": tracked_state,
        "ground_track": ground_track(tracked_record, now=moment) if tracked_record else [],
        "subsolar": subsolar_point(moment),
        "satellites": states,
        "visible_count": sum(1 for state in states if state["visible"]),
        "total_count": len(states),
        "stale": any(state["stale"] for state in states),
    }
