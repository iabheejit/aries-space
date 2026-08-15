import os
from math import isfinite


class ConfigurationError(ValueError):
    pass


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or "replace-with-" in value:
        raise ConfigurationError(f"{name} must be configured")
    return value


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def _validate_range(name: str, value: float, minimum: float, maximum: float) -> float:
    if not isfinite(value) or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _validate_positive(name: str, value: int) -> int:
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


NORAD_ID = _int_env("NORAD_ID", 68635)
SATELLITE_NAME = os.environ.get("SATELLITE_NAME", "CANVAS")
STATION_NAME = os.environ.get("STATION_NAME", "GHRCE campus (approx.)")
STATION_LAT = _validate_range("STATION_LAT", _float_env("STATION_LAT", 21.1052484), -90, 90)
STATION_LON = _validate_range("STATION_LON", _float_env("STATION_LON", 79.0034903), -180, 180)
STATION_ELEV_M = _float_env("STATION_ELEV_M", 310.0)
if not isfinite(STATION_ELEV_M):
    raise ConfigurationError("STATION_ELEV_M must be finite")

CELESTRAK_URL = os.environ.get("CELESTRAK_URL", "https://celestrak.org/NORAD/elements/gp.php")
SATNOGS_OBSERVATIONS_URL = os.environ.get(
    "SATNOGS_OBSERVATIONS_URL", "https://network.satnogs.org/api/observations/"
)
SATNOGS_MAX_RESPONSE_BYTES = _validate_positive(
    "SATNOGS_MAX_RESPONSE_BYTES", _int_env("SATNOGS_MAX_RESPONSE_BYTES", 10_000_000)
)
SATNOGS_FIXTURE_PATH = os.environ.get("SATNOGS_FIXTURE_PATH") or None
TLE_REFRESH_HOURS = _validate_positive("TLE_REFRESH_HOURS", _int_env("TLE_REFRESH_HOURS", 12))
OBS_POLL_MINUTES = _int_env("OBS_POLL_MINUTES", 10)
if OBS_POLL_MINUTES < 5:
    raise ConfigurationError("OBS_POLL_MINUTES must be at least 5")
SCHEDULER_ENABLED = _bool_env("SCHEDULER_ENABLED", True)
READINESS_TIMEOUT_SECONDS = _validate_positive(
    "READINESS_TIMEOUT_SECONDS", _int_env("READINESS_TIMEOUT_SECONDS", 2)
)

DATABASE_URL = _required_env("DATABASE_URL")
if not DATABASE_URL.startswith("postgresql+psycopg://"):
    raise ConfigurationError("DATABASE_URL must use postgresql+psycopg")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = _required_env("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = _required_env("MINIO_SECRET_KEY")
MINIO_SECURE = _bool_env("MINIO_SECURE", False)
MINIO_RAW_BUCKET = "raw"
MINIO_BUCKETS = (MINIO_RAW_BUCKET, "processed", "results")
API_BEARER_TOKEN = _required_env("API_BEARER_TOKEN")