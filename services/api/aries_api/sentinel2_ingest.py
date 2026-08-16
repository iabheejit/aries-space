import hashlib
import logging
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

# Placeholder Area-of-Interest identifier. There is no AOI catalog table yet
# (that is future roadmap work — see biz/orbital-compute-access-plan.md /
# the "Expand Evidence Inputs" milestone); this fixed id just satisfies the
# Dataset schema's "must have a satellite or an AOI subject" constraint for
# a single documented AOI (GHRCE region, Nagpur agricultural cropland).
AOI_ID = 1


def _read_crop_from_fixture(fixture_path: str) -> bytes:
    return Path(fixture_path).read_bytes()


def _read_crop_live(red_href: str, nir_href: str, window: Window) -> bytes:
    with rasterio.open(f"/vsicurl/{red_href}") as red_src:
        red = red_src.read(1, window=window)
        transform = red_src.window_transform(window)
        crs = red_src.crs
    with rasterio.open(f"/vsicurl/{nir_href}") as nir_src:
        nir = nir_src.read(1, window=window)

    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "width": int(window.width),
        "height": int(window.height),
        "count": 2,
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
    }
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            dst.write(red, 1)
            dst.write(nir, 2)
        return bytes(memfile.read())


def fetch_sentinel2_crop() -> bytes:
    """Fetch a real Sentinel-2 L2A red/NIR crop, or read one from a fixture
    for deterministic offline use (mirrors SATNOGS_FIXTURE_PATH).
    """
    if config.SENTINEL2_FIXTURE_PATH is not None:
        return _read_crop_from_fixture(config.SENTINEL2_FIXTURE_PATH)
    window = Window(
        config.SENTINEL2_CROP_COL_OFF,
        config.SENTINEL2_CROP_ROW_OFF,
        config.SENTINEL2_CROP_WIDTH,
        config.SENTINEL2_CROP_HEIGHT,
    )
    try:
        return _read_crop_live(config.SENTINEL2_RED_HREF, config.SENTINEL2_NIR_HREF, window)
    except Exception as exc:
        raise IngestUnavailableError("Sentinel-2 crop is unavailable") from exc


def ingest_sentinel2_crop(session: Session, store: ObjectStore, payload: bytes):
    """Store a Sentinel-2 red/NIR crop as a checksum-verified Dataset,
    deduplicated on (source, external_id) exactly like SatNOGS ingestion.
    """
    external_id = (
        f"{config.SENTINEL2_ITEM_ID}:{config.SENTINEL2_CROP_COL_OFF}_"
        f"{config.SENTINEL2_CROP_ROW_OFF}_{config.SENTINEL2_CROP_WIDTH}_"
        f"{config.SENTINEL2_CROP_HEIGHT}"
    )
    checksum = hashlib.sha256(payload).hexdigest()
    key = f"sentinel2/{config.SENTINEL2_ITEM_ID}/{external_id.split(':', 1)[1]}.tif"
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
        observed_at=config.SENTINEL2_OBSERVED_AT,
        size_bytes=len(payload),
        object_key=key,
        sha256=checksum,
        ingested_at=ingested_at,
        aoi_id=AOI_ID,
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
