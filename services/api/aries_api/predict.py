from datetime import datetime
from typing import TypedDict

from skyfield.api import EarthSatellite, load, wgs84

from services.api.aries_api.tle import TLERecord

_COMPASS_POINTS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _compass(azimuth_degrees: float) -> str:
    return _COMPASS_POINTS[round(azimuth_degrees / 22.5) % 16]


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
) -> list[PredictedPass]:
    timescale = load.timescale()
    satellite = EarthSatellite(tle.line1, tle.line2, tle.name, timescale)
    observer = wgs84.latlon(lat, lon, elevation_m=elev_m)
    start = timescale.now()
    end = timescale.tt_jd(start.tt + search_hours / 24)
    times, events = satellite.find_events(observer, start, end, altitude_degrees=min_elevation_deg)
    difference = satellite - observer
    passes: list[PredictedPass] = []
    aos_time = aos_azimuth = max_elevation = None
    for time, event in zip(times, events):
        altitude, azimuth, _ = difference.at(time).altaz()
        if event == 0:
            aos_time = time.utc_datetime()
            aos_azimuth = azimuth.degrees
            max_elevation = altitude.degrees
        elif event == 1 and (max_elevation is None or altitude.degrees > max_elevation):
            max_elevation = altitude.degrees
        elif event == 2 and aos_time is not None:
            passes.append(
                PredictedPass(
                    aos=aos_time,
                    los=time.utc_datetime(),
                    max_elevation_deg=round(float(max_elevation), 2),
                    direction=f"{_compass(aos_azimuth)} -> {_compass(azimuth.degrees)}",
                    tle_stale=tle.stale,
                )
            )
            aos_time = aos_azimuth = max_elevation = None
            if len(passes) >= count:
                break
    return passes