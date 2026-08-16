import os
from datetime import datetime, timezone
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

DOWNLINK_MBPS = _validate_positive("DOWNLINK_MBPS", _int_env("DOWNLINK_MBPS", 100))
ELECTRICITY_INR_PER_KWH = _float_env("ELECTRICITY_INR_PER_KWH", 8.0)
DOWNLINK_INR_PER_GB = _float_env("DOWNLINK_INR_PER_GB", 500.0)
GROUND_COMPUTE_INR_PER_HOUR = _float_env("GROUND_COMPUTE_INR_PER_HOUR", 100.0)
GROUND_ESTIMATED_WATTS = _float_env("GROUND_ESTIMATED_WATTS", 25.0)
EDGE_SIM_WATTS = _float_env("EDGE_SIM_WATTS", 15.0)
EDGE_SIM_SLOWDOWN_FACTOR = _float_env("EDGE_SIM_SLOWDOWN_FACTOR", 4.0)
BENCHMARK_TIMEOUT_SECONDS = _validate_positive(
    "BENCHMARK_TIMEOUT_SECONDS", _int_env("BENCHMARK_TIMEOUT_SECONDS", 10)
)
BENCHMARK_SAMPLE_ITERATIONS = _validate_positive(
    "BENCHMARK_SAMPLE_ITERATIONS", _int_env("BENCHMARK_SAMPLE_ITERATIONS", 1000)
)
# Raster workloads (e.g. Sentinel-2 NDVI) cost orders of magnitude more per
# call than the tiny JSON-metadata SatNOGS proxy; a much smaller sample count
# keeps the ground-cpu median measurement inside BENCHMARK_TIMEOUT_SECONDS.
SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS = _validate_positive(
    "SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS", _int_env("SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS", 15)
)
# Sentinel-2 L2A crop (AWS Open Data, no-sign-request): default scene is a
# real, low-cloud (<2%) tile over the GHRCE/Nagpur agricultural region,
# resolved 2026-08-16 via https://earth-search.aws.element84.com/v1.
SENTINEL2_ITEM_ID = os.environ.get("SENTINEL2_ITEM_ID", "S2C_43QHD_20260619_0_L2A")
SENTINEL2_RED_HREF = os.environ.get(
    "SENTINEL2_RED_HREF",
    "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/43/Q/HD/2026/6/S2C_43QHD_20260619_0_L2A/B04.tif",
)
SENTINEL2_NIR_HREF = os.environ.get(
    "SENTINEL2_NIR_HREF",
    "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/43/Q/HD/2026/6/S2C_43QHD_20260619_0_L2A/B08.tif",
)
SENTINEL2_OBSERVED_AT = datetime.fromisoformat(
    os.environ.get("SENTINEL2_OBSERVED_AT", "2026-06-19T05:33:00.760000+00:00")
)
if SENTINEL2_OBSERVED_AT.tzinfo is None:
    SENTINEL2_OBSERVED_AT = SENTINEL2_OBSERVED_AT.replace(tzinfo=timezone.utc)
SENTINEL2_CROP_COL_OFF = _int_env("SENTINEL2_CROP_COL_OFF", 5000)
SENTINEL2_CROP_ROW_OFF = _int_env("SENTINEL2_CROP_ROW_OFF", 5000)
SENTINEL2_CROP_WIDTH = _validate_positive("SENTINEL2_CROP_WIDTH", _int_env("SENTINEL2_CROP_WIDTH", 1024))
SENTINEL2_CROP_HEIGHT = _validate_positive("SENTINEL2_CROP_HEIGHT", _int_env("SENTINEL2_CROP_HEIGHT", 1024))
SENTINEL2_FIXTURE_PATH = os.environ.get("SENTINEL2_FIXTURE_PATH") or None
SENTINEL2_FETCH_TIMEOUT_SECONDS = _validate_positive(
    "SENTINEL2_FETCH_TIMEOUT_SECONDS", _int_env("SENTINEL2_FETCH_TIMEOUT_SECONDS", 20)
)

# Second Sentinel-2 scene: real, low-cloud (<3%) tile over Mumbai/JNPT
# coastal water, resolved 2026-08-16 via the same STAC API, for ship-detect.
SENTINEL2_COASTAL_ITEM_ID = os.environ.get(
    "SENTINEL2_COASTAL_ITEM_ID", "S2A_43QBA_20260428_0_L2A"
)
SENTINEL2_COASTAL_NIR_HREF = os.environ.get(
    "SENTINEL2_COASTAL_NIR_HREF",
    "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/43/Q/BA/2026/4/S2A_43QBA_20260428_0_L2A/B08.tif",
)
SENTINEL2_COASTAL_OBSERVED_AT = datetime.fromisoformat(
    os.environ.get("SENTINEL2_COASTAL_OBSERVED_AT", "2026-04-28T05:54:10.923000+00:00")
)
if SENTINEL2_COASTAL_OBSERVED_AT.tzinfo is None:
    SENTINEL2_COASTAL_OBSERVED_AT = SENTINEL2_COASTAL_OBSERVED_AT.replace(tzinfo=timezone.utc)
SENTINEL2_COASTAL_CROP_COL_OFF = _int_env("SENTINEL2_COASTAL_CROP_COL_OFF", 0)
SENTINEL2_COASTAL_CROP_ROW_OFF = _int_env("SENTINEL2_COASTAL_CROP_ROW_OFF", 0)
SENTINEL2_COASTAL_CROP_WIDTH = _validate_positive(
    "SENTINEL2_COASTAL_CROP_WIDTH", _int_env("SENTINEL2_COASTAL_CROP_WIDTH", 1024)
)
SENTINEL2_COASTAL_CROP_HEIGHT = _validate_positive(
    "SENTINEL2_COASTAL_CROP_HEIGHT", _int_env("SENTINEL2_COASTAL_CROP_HEIGHT", 1024)
)
SENTINEL2_COASTAL_FIXTURE_PATH = os.environ.get("SENTINEL2_COASTAL_FIXTURE_PATH") or None

for name, value in (
    ("ELECTRICITY_INR_PER_KWH", ELECTRICITY_INR_PER_KWH),
    ("DOWNLINK_INR_PER_GB", DOWNLINK_INR_PER_GB),
    ("GROUND_COMPUTE_INR_PER_HOUR", GROUND_COMPUTE_INR_PER_HOUR),
    ("GROUND_ESTIMATED_WATTS", GROUND_ESTIMATED_WATTS),
    ("EDGE_SIM_WATTS", EDGE_SIM_WATTS),
    ("EDGE_SIM_SLOWDOWN_FACTOR", EDGE_SIM_SLOWDOWN_FACTOR),
):
    if not isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be a positive finite number")