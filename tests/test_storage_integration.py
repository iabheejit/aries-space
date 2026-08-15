import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from minio import Minio
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from services.api.aries_api import config
from services.api.aries_api.ingest import IngestUnavailableError, ingest_satnogs_observation
from services.api.aries_api.models import Dataset, Observation
from services.api.aries_api.storage import ObjectNotFoundError, ObjectStore

DATABASE_URL = os.environ.get("ARIES_INTEGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="PostgreSQL/MinIO integration environment is not configured",
)


def _raw_observation(observation_id: int) -> dict:
    path = Path(__file__).parent / "fixtures" / "satnogs_observation_14790266.json"
    payload = json.loads(path.read_text())
    payload["id"] = observation_id
    return payload


def _store() -> ObjectStore:
    return ObjectStore(
        Minio(
            os.environ.get("ARIES_INTEGRATION_MINIO_ENDPOINT", "127.0.0.1:9000"),
            access_key=os.environ.get("MINIO_ACCESS_KEY", "aries"),
            secret_key=os.environ.get("MINIO_SECRET_KEY", "aries-development-only"),
            secure=False,
        )
    )


def _cleanup(session_factory, store: ObjectStore, observation_id: int) -> None:
    external_id = str(observation_id)
    key = f"satnogs/68635/{external_id}.json"
    with session_factory() as session:
        dataset_ids = select(Dataset.id).where(
            Dataset.source == "satnogs", Dataset.external_id == external_id
        )
        session.execute(delete(Observation).where(Observation.dataset_id.in_(dataset_ids)))
        session.execute(
            delete(Dataset).where(
                Dataset.source == "satnogs", Dataset.external_id == external_id
            )
        )
        session.commit()
    store.delete(config.MINIO_RAW_BUCKET, key)


def test_concurrent_ingest_keeps_winning_row_and_object():
    observation_id = 1_990_000_001
    raw = _raw_observation(observation_id)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    store = _store()
    store.ensure_buckets()
    _cleanup(sessions, store, observation_id)
    barrier = Barrier(2)

    def ingest():
        with sessions() as session:
            barrier.wait(timeout=5)
            return ingest_satnogs_observation(session, store, raw, 68635)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: ingest(), range(2)))

        with sessions() as session:
            row_count = session.scalar(
                select(func.count()).select_from(Dataset).where(
                    Dataset.source == "satnogs",
                    Dataset.external_id == str(observation_id),
                )
            )
        key = f"satnogs/68635/{observation_id}.json"
        payload = store.get(config.MINIO_RAW_BUCKET, key)
        assert row_count == 1
        assert sorted(result.created for result in results) == [False, True]
        assert hashlib.sha256(payload).hexdigest() == results[0].sha256
    finally:
        _cleanup(sessions, store, observation_id)
        engine.dispose()


def test_real_store_preserves_preexisting_object_when_commit_fails(monkeypatch):
    observation_id = 1_990_000_002
    raw = _raw_observation(observation_id)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    store = _store()
    store.ensure_buckets()
    _cleanup(sessions, store, observation_id)
    payload = json.dumps(
        raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    checksum = hashlib.sha256(payload).hexdigest()
    key = f"satnogs/68635/{observation_id}.json"
    store.put(config.MINIO_RAW_BUCKET, key, payload, checksum)

    try:
        with sessions() as session:
            monkeypatch.setattr(
                session,
                "commit",
                lambda: (_ for _ in ()).throw(SQLAlchemyError("forced commit failure")),
            )
            with pytest.raises(IngestUnavailableError, match="Database commit failed"):
                ingest_satnogs_observation(session, store, raw, 68635)

        assert store.get(config.MINIO_RAW_BUCKET, key) == payload
        with sessions() as session:
            assert session.scalar(
                select(func.count()).select_from(Dataset).where(
                    Dataset.external_id == str(observation_id)
                )
            ) == 0
    finally:
        _cleanup(sessions, store, observation_id)
        engine.dispose()
