import json
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.api.aries_api import config
from services.api.aries_api.ingest import (
    IngestConflictError,
    IngestUnavailableError,
    OrphanObjectError,
    ingest_satnogs_observation,
)
from services.api.aries_api.models import Base, Dataset
from services.api.aries_api.storage import ObjectInfo, ObjectNotFoundError


@pytest.fixture
def raw_observation():
    path = Path(__file__).parent / "fixtures" / "satnogs_observation_14790266.json"
    return json.loads(path.read_text())


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
        self.delete_failure = None
        self.timeout_after_write = False
        self.timeout_payload = None

    def stat(self, bucket, key):
        try:
            payload, checksum = self.objects[(bucket, key)]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc
        return ObjectInfo(len(payload), checksum)

    def put(self, bucket, key, payload, sha256):
        if self.put_failure is not None:
            raise self.put_failure
        stored_payload = self.timeout_payload if self.timeout_payload is not None else payload
        self.objects[(bucket, key)] = (stored_payload, sha256)
        if self.timeout_after_write:
            raise TimeoutError("ambiguous upload")

    def delete(self, bucket, key):
        if self.delete_failure is not None:
            raise self.delete_failure
        self.objects.pop((bucket, key), None)

    def get(self, bucket, key):
        try:
            return self.objects[(bucket, key)][0]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc


def test_ingest_is_deterministic_and_idempotent(session, raw_observation):
    store = MemoryStore()

    created = ingest_satnogs_observation(session, store, raw_observation, 68635)
    repeated = ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert created.created is True
    assert repeated.created is False
    assert repeated == type(repeated)(**{**created.__dict__, "created": False})
    assert created.object_key == "satnogs/68635/14790266.json"
    assert session.scalar(select(func.count()).select_from(Dataset)) == 1
    assert len(store.objects) == 1


def test_definitive_upload_failure_leaves_no_row_or_object(session, raw_observation):
    store = MemoryStore()
    store.put_failure = RuntimeError("minio unavailable")

    with pytest.raises(IngestUnavailableError, match="upload failed"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert session.scalar(select(func.count()).select_from(Dataset)) == 0
    assert store.objects == {}


def test_upload_timeout_with_matching_object_continues(session, raw_observation):
    store = MemoryStore()
    store.timeout_after_write = True

    result = ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert result.created is True
    assert session.scalar(select(func.count()).select_from(Dataset)) == 1
    assert len(store.objects) == 1


def test_upload_timeout_without_object_leaves_no_row(session, raw_observation):
    store = MemoryStore()
    store.put_failure = TimeoutError("ambiguous upload")

    with pytest.raises(IngestUnavailableError, match="timed out"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert session.scalar(select(func.count()).select_from(Dataset)) == 0
    assert store.objects == {}


def test_upload_timeout_with_mismatching_object_leaves_no_row(session, raw_observation):
    store = MemoryStore()
    store.timeout_after_write = True
    store.timeout_payload = b"mismatching bytes"

    with pytest.raises(IngestConflictError, match="differs after upload timeout"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert session.scalar(select(func.count()).select_from(Dataset)) == 0
    assert len(store.objects) == 1


def test_existing_object_read_outage_is_unavailable(session, raw_observation):
    store = MemoryStore()
    ingest_satnogs_observation(session, store, raw_observation, 68635)
    store.get = lambda *_: (_ for _ in ()).throw(RuntimeError("minio unavailable"))

    with pytest.raises(IngestUnavailableError, match="could not be verified"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)


def test_existing_object_stat_outage_is_unavailable(session, raw_observation):
    store = MemoryStore()
    ingest_satnogs_observation(session, store, raw_observation, 68635)
    store.stat = lambda *_: (_ for _ in ()).throw(RuntimeError("minio unavailable"))

    with pytest.raises(IngestUnavailableError, match="could not be verified"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)


def test_preexisting_mismatch_refuses_without_mutation(session, raw_observation):
    store = MemoryStore()
    key = (config.MINIO_RAW_BUCKET, "satnogs/68635/14790266.json")
    store.objects[key] = (b"different", "0" * 64)

    with pytest.raises(IngestConflictError, match="differs"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert session.scalar(select(func.count()).select_from(Dataset)) == 0
    assert store.objects[key][0] == b"different"


def test_preexisting_forged_metadata_refuses_object_bytes(session, raw_observation):
    store = MemoryStore()
    key = (config.MINIO_RAW_BUCKET, "satnogs/68635/14790266.json")
    expected_size = len(
        json.dumps(
            raw_observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )
    store.objects[key] = (b"x" * expected_size, "94591a7ab126058ce1c0a0a81c6b7aff35f223ec5f429ccd92a25ee13f17f98f")

    with pytest.raises(IngestConflictError, match="differs"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert session.scalar(select(func.count()).select_from(Dataset)) == 0


def test_commit_failure_deletes_new_object(session, raw_observation, monkeypatch):
    store = MemoryStore()

    def fail_commit():
        raise SQLAlchemyError("forced commit failure")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(IngestUnavailableError, match="Database commit failed"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert store.objects == {}
    assert session.scalar(select(func.count()).select_from(Dataset)) == 0


def test_commit_failure_preserves_preexisting_matching_object(
    session, raw_observation, monkeypatch
):
    store = MemoryStore()
    payload = json.dumps(
        raw_observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    key = (config.MINIO_RAW_BUCKET, "satnogs/68635/14790266.json")
    store.objects[key] = (payload, __import__("hashlib").sha256(payload).hexdigest())
    monkeypatch.setattr(
        session,
        "commit",
        lambda: (_ for _ in ()).throw(SQLAlchemyError("forced commit failure")),
    )

    with pytest.raises(IngestUnavailableError, match="Database commit failed"):
        ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert store.objects[key][0] == payload
    assert session.scalar(select(func.count()).select_from(Dataset)) == 0


def test_cleanup_failure_logs_orphan_and_leaves_no_row(
    session, raw_observation, monkeypatch, caplog
):
    store = MemoryStore()
    store.delete_failure = RuntimeError("delete unavailable")
    monkeypatch.setattr(
        session,
        "commit",
        lambda: (_ for _ in ()).throw(SQLAlchemyError("forced commit failure")),
    )

    with caplog.at_level(logging.ERROR, logger="aries.ingest"):
        with pytest.raises(OrphanObjectError):
            ingest_satnogs_observation(session, store, raw_observation, 68635)

    assert "orphan_object bucket=raw key=satnogs/68635/14790266.json" in caplog.text
    assert session.scalar(select(func.count()).select_from(Dataset)) == 0
    assert len(store.objects) == 1