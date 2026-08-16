import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.windows import Window
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.api.aries_api import config
from services.api.aries_api.ingest import IngestUnavailableError, _lock_ingestion, _matching, _result
from services.api.aries_api.models import Dataset
from services.api.aries_api.storage import ObjectNotFoundError, ObjectStore

logger = logging.getLogger("aries.sentinel2_ingest")

# There is no AOI catalog table yet (that is further roadmap work); these
# fixed ids are a small, explicit, documented registry -- not a generic
# rules engine -- that gives the existing Dataset.aoi_id column real
# meaning so workloads can be restricted to the right scene (see
# WorkloadSpec.eligible_aoi_ids in benchmarks.py).
AOI_GHRCE_AGRICULTURAL = 1  # Nagpur agricultural cropland, GHRCE region
AOI_COASTAL_PORT = 2  # Mumbai/JNPT coastal water, ship-detect target


@dataclass(frozen=True)
class SceneConfig:
    aoi_id: int
    aoi_name: str
    item_id: str
    band_hrefs: tuple[str, ...]  # ordered; band 1, band 2, ...
    window: Window
    observed_at: datetime
    fixture_path: str | None


def _scene_registry() -> dict[int, SceneConfig]:
    return {
        AOI_GHRCE_AGRICULTURAL: SceneConfig(
            aoi_id=AOI_GHRCE_AGRICULTURAL,
            aoi_name="ghrce-agricultural",
            item_id=config.SENTINEL2_ITEM_ID,
            band_hrefs=(config.SENTINEL2_RED_HREF, config.SENTINEL2_NIR_HREF),
            window=Window(
                config.SENTINEL2_CROP_COL_OFF,
                config.SENTINEL2_CROP_ROW_OFF,
                config.SENTINEL2_CROP_WIDTH,
                config.SENTINEL2_CROP_HEIGHT,
            ),
            observed_at=config.SENTINEL2_OBSERVED_AT,
            fixture_path=config.SENTINEL2_FIXTURE_PATH,
        ),
        AOI_COASTAL_PORT: SceneConfig(
            aoi_id=AOI_COASTAL_PORT,
            aoi_name="coastal-port",
            item_id=config.SENTINEL2_COASTAL_ITEM_ID,
            band_hrefs=(config.SENTINEL2_COASTAL_NIR_HREF,),
            window=Window(
                config.SENTINEL2_COASTAL_CROP_COL_OFF,
                config.SENTINEL2_COASTAL_CROP_ROW_OFF,
                config.SENTINEL2_COASTAL_CROP_WIDTH,
                config.SENTINEL2_COASTAL_CROP_HEIGHT,
            ),
            observed_at=config.SENTINEL2_COASTAL_OBSERVED_AT,
            fixture_path=config.SENTINEL2_COASTAL_FIXTURE_PATH,
        ),
    }


def _read_crop_from_fixture(fixture_path: str) -> bytes:
    return Path(fixture_path).read_bytes()


def _read_crop_live(scene: SceneConfig) -> bytes:
    # GDAL's /vsicurl/ has no timeout by default -- a stalled upstream
    # response would otherwise hang the fetching thread indefinitely.
    gdal_env = rasterio.Env(
        GDAL_HTTP_TIMEOUT=config.SENTINEL2_FETCH_TIMEOUT_SECONDS,
        GDAL_HTTP_CONNECTTIMEOUT=config.SENTINEL2_FETCH_TIMEOUT_SECONDS,
    )
    bands = []
    transform = None
    crs = None
    with gdal_env:
        for href in scene.band_hrefs:
            with rasterio.open(f"/vsicurl/{href}") as src:
                bands.append(src.read(1, window=scene.window))
                if transform is None:
                    transform = src.window_transform(scene.window)
                    crs = src.crs

    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "width": int(scene.window.width),
        "height": int(scene.window.height),
        "count": len(bands),
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
    }
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            for index, band in enumerate(bands, start=1):
                dst.write(band, index)
        return bytes(memfile.read())


def fetch_sentinel2_crop(aoi_id: int) -> bytes:
    """Fetch a real Sentinel-2 L2A crop for the given AOI, or read one from
    a fixture for deterministic offline use (mirrors SATNOGS_FIXTURE_PATH).
    """
    scene = _scene_registry()[aoi_id]
    if scene.fixture_path is not None:
        return _read_crop_from_fixture(scene.fixture_path)
    try:
        return _read_crop_live(scene)
    except Exception as exc:
        logger.warning(
            "sentinel2_fetch_failed aoi_id=%s item=%s: %s", aoi_id, scene.item_id, exc
        )
        raise IngestUnavailableError("Sentinel-2 crop is unavailable") from exc


def ingest_sentinel2_crop(session: Session, store: ObjectStore, payload: bytes, aoi_id: int):
    """Store a Sentinel-2 crop as a checksum-verified Dataset, deduplicated
    on (source, external_id) exactly like SatNOGS ingestion. external_id
    and object key are scoped by AOI so scenes never collide.
    """
    scene = _scene_registry()[aoi_id]
    external_id = (
        f"{scene.item_id}:{int(scene.window.col_off)}_{int(scene.window.row_off)}_"
        f"{int(scene.window.width)}_{int(scene.window.height)}"
    )
    checksum = hashlib.sha256(payload).hexdigest()
    key = f"sentinel2/{scene.item_id}/{external_id.split(':', 1)[1]}.tif"
    _lock_ingestion(session, "sentinel2", external_id)

    existing = session.scalar(
        select(Dataset).where(Dataset.source == "sentinel2", Dataset.external_id == external_id)
    )
    if existing is not None:
        try:
            info = store.stat(config.MINIO_RAW_BUCKET, existing.object_key)
            object_matches = _matching(
                store, config.MINIO_RAW_BUCKET, existing.object_key, info,
                existing.size_bytes, existing.sha256,
            )
        except ObjectNotFoundError as exc:
            raise IngestUnavailableError("Dataset object is missing") from exc
        except Exception as exc:
            raise IngestUnavailableError("Dataset object could not be verified") from exc
        if (
            existing.object_key != key
            or existing.size_bytes != len(payload)
            or existing.sha256 != checksum
            or not object_matches
        ):
            raise IngestUnavailableError("Dataset object checksum or size differs")
        return _result(existing, created=False)

    object_created = False
    try:
        info = store.stat(config.MINIO_RAW_BUCKET, key)
    except ObjectNotFoundError:
        try:
            store.put(config.MINIO_RAW_BUCKET, key, payload, checksum)
            object_created = True
        except Exception as exc:
            raise IngestUnavailableError("Object upload failed") from exc
    except Exception as exc:
        raise IngestUnavailableError("Object lookup failed") from exc
    else:
        try:
            object_matches = _matching(
                store, config.MINIO_RAW_BUCKET, key, info, len(payload), checksum
            )
        except Exception as exc:
            raise IngestUnavailableError("Existing object could not be verified") from exc
        if not object_matches:
            raise IngestUnavailableError("Existing object checksum or size differs")

    ingested_at = datetime.now(timezone.utc)
    dataset = Dataset(
        source="sentinel2",
        external_id=external_id,
        observed_at=scene.observed_at,
        size_bytes=len(payload),
        object_key=key,
        sha256=checksum,
        ingested_at=ingested_at,
        aoi_id=scene.aoi_id,
    )
    session.add(dataset)
    try:
        session.flush()
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        if object_created:
            try:
                store.delete(config.MINIO_RAW_BUCKET, key)
            except Exception as delete_exc:
                logger.error(
                    "orphan_object bucket=%s key=%s", config.MINIO_RAW_BUCKET, key,
                    exc_info=delete_exc,
                )
        raise IngestUnavailableError("Database commit failed") from exc

    return _result(dataset, created=True)
