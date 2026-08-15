from datetime import datetime
from typing import List, TypedDict

from skyfield.api import EarthSatellite, load, wgs84

from app.tle import TLERecord

_COMPASS_POINTS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _compass(azimuth_degrees: float) -> str:
    index = round(azimuth_degrees / 22.5) % 16
    return _COMPASS_POINTS[index]


class PredictedPass(TypedDict):
    aos: datetime
    los: datetime
    max_elevation_deg: float
    direction: str
    tle_stale: bool


def compute_passes(
    tle: TLERecord,
    lat: float,
    lon: float,
    elev_m: float,
    count: int = 5,
    search_hours: int = 72,
    min_elevation_deg: float = 10.0,
) -> List[PredictedPass]:
    """Compute the next `count` passes above min_elevation_deg within the
    next `search_hours`, using the given TLE. Pure two-body geometry from
    the satellite's own elements — no external ephemeris file needed.
    """
    ts = load.timescale()
    satellite = EarthSatellite(tle.line1, tle.line2, tle.name, ts)
    observer = wgs84.latlon(lat, lon, elevation_m=elev_m)

    t0 = ts.now()
    t1 = ts.tt_jd(t0.tt + search_hours / 24)
    times, events = satellite.find_events(
        observer, t0, t1, altitude_degrees=min_elevation_deg
    )

    difference = satellite - observer
    passes: List[PredictedPass] = []
    aos_time = None
    aos_az = None
    max_elevation = None

    for t, event in zip(times, events):
        alt, az, _ = difference.at(t).altaz()
        if event == 0:  # rise
            aos_time = t.utc_datetime()
            aos_az = az.degrees
            max_elevation = alt.degrees
        elif event == 1:  # culminate
            if max_elevation is None or alt.degrees > max_elevation:
                max_elevation = alt.degrees
        elif event == 2:  # set
            if aos_time is None:
                continue  # pass was already in progress at t0; skip partial
            los_time = t.utc_datetime()
            los_az = az.degrees
            passes.append(
                PredictedPass(
                    aos=aos_time,
                    los=los_time,
                    max_elevation_deg=round(float(max_elevation), 2),
                    direction=f"{_compass(aos_az)} -> {_compass(los_az)}",
                    tle_stale=tle.stale,
                )
            )
            aos_time = None
            aos_az = None
            max_elevation = None
            if len(passes) >= count:
                break

    return passes[:count]
