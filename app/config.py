import os


def _float_env(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _int_env(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


NORAD_ID = _int_env("NORAD_ID", 68635)
SATELLITE_NAME = os.environ.get("SATELLITE_NAME", "CANVAS")

# GHRCE (G H Raisoni College of Engineering, Nagpur) approximate public
# coordinates. GHRCE has no registered station in the SatNOGS network
# (confirmed 2026-08-15), so this is a placeholder pending confirmation
# of exact rooftop/antenna coordinates.
STATION_LAT = _float_env("STATION_LAT", 21.1237)
STATION_LON = _float_env("STATION_LON", 79.0353)
STATION_ELEV_M = _float_env("STATION_ELEV_M", 310.0)
STATION_NAME = os.environ.get("STATION_NAME", "GHRCE (approx.)")

CELESTRAK_URL = os.environ.get(
    "CELESTRAK_URL", "https://celestrak.org/NORAD/elements/gp.php"
)
SATNOGS_OBSERVATIONS_URL = os.environ.get(
    "SATNOGS_OBSERVATIONS_URL", "https://network.satnogs.org/api/observations/"
)

TLE_REFRESH_HOURS = _int_env("TLE_REFRESH_HOURS", 12)
OBS_POLL_MINUTES = _int_env("OBS_POLL_MINUTES", 10)

DB_PATH = os.environ.get("DB_PATH", "missionops.db")
DB_URL = f"sqlite:///{DB_PATH}"
