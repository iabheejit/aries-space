from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from services.api.aries_api.ingest import IngestUnavailableError
from services.api.aries_api.models import Base, Dataset
from services.api.aries_api.sentinel2_ingest import (
    AOI_COASTAL_PORT,
    AOI_GHRCE_AGRICULTURAL,
    ingest_sentinel2_crop,
)
from services.api.aries_api.storage import ObjectInfo, ObjectNotFoundError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sentinel2_crop_43QHD_128.tif"
COASTAL_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "sentinel2_crop_43QBA_coastal_128.tif"
)


@pytest.fixture
def crop_bytes():
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def coastal_crop_bytes():
    return COASTAL_FIXTURE_PATH.read_bytes()


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as value:
        yield value


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.put_failure = None

    def stat(self, bucket, key):
        try:
            payload, checksum = self.objects[(bucket, key)]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc
        return ObjectInfo(len(payload), checksum)

    def put(self, bucket, key, payload, sha256):
        if self.put_failure is not None:
            raise self.put_failure
        self.objects[(bucket, key)] = (payload, sha256)

    def get(self, bucket, key):
        try:
            return self.objects[(bucket, key)][0]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc

    def delete(self, bucket, key):
        self.objects.pop((bucket, key), None)


def test_ingest_is_deterministic_and_idempotent(session, crop_bytes):
    store = MemoryStore()

    created = ingest_sentinel2_crop(session, store, crop_bytes, AOI_GHRCE_AGRICULTURAL)
    repeated = ingest_sentinel2_crop(session, store, crop_bytes, AOI_GHRCE_AGRICULTURAL)

    assert created.created is True
    assert repeated.created is False
    assert created.dataset_id == repeated.dataset_id
    assert session.scalar(select(func.count()).select_from(Dataset)) == 1
    assert len(store.objects) == 1

    dataset = session.get(Dataset, created.dataset_id)
    assert dataset.source == "sentinel2"
    assert dataset.aoi_id == AOI_GHRCE_AGRICULTURAL
    assert dataset.satellite_norad_id is None
    assert dataset.size_bytes == len(crop_bytes)


def test_ingest_second_aoi_is_distinct_from_first(session, crop_bytes, coastal_crop_bytes):
    store = MemoryStore()

    agricultural = ingest_sentinel2_crop(
        session, store, crop_bytes, AOI_GHRCE_AGRICULTURAL
    )
    coastal = ingest_sentinel2_crop(session, store, coastal_crop_bytes, AOI_COASTAL_PORT)

    assert agricultural.dataset_id != coastal.dataset_id
    assert session.scalar(select(func.count()).select_from(Dataset)) == 2
    coastal_dataset = session.get(Dataset, coastal.dataset_id)
    assert coastal_dataset.aoi_id == AOI_COASTAL_PORT
    assert coastal_dataset.external_id != agricultural.external_id


def test_upload_failure_leaves_no_row_or_object(session, crop_bytes):
    store = MemoryStore()
    store.put_failure = RuntimeError("minio unavailable")

    with pytest.raises(IngestUnavailableError, match="upload failed"):
        ingest_sentinel2_crop(session, store, crop_bytes, AOI_GHRCE_AGRICULTURAL)

    assert session.scalar(select(func.count()).select_from(Dataset)) == 0
    assert store.objects == {}
