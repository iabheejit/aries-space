import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from urllib3.exceptions import ReadTimeoutError

from services.api.aries_api import config
from services.api.aries_api.models import Dataset, Observation
from services.api.aries_api.normalize import normalize_observation
from services.api.aries_api.storage import ObjectInfo, ObjectNotFoundError, ObjectStore

logger = logging.getLogger("aries.ingest")


class IngestConflictError(Exception):
    pass


class IngestUnavailableError(Exception):
    pass


class OrphanObjectError(IngestUnavailableError):
    pass


@dataclass(frozen=True)
class IngestResult:
    dataset_id: int
    external_id: str
    object_key: str
    size_bytes: int
    sha256: str
    created: bool


def fetch_observation(norad_id: int, limit: int = 1, observation_id: int | None = None) -> dict:
    try:
        if config.SATNOGS_FIXTURE_PATH is not None:
            payload = json.loads(Path(config.SATNOGS_FIXTURE_PATH).read_text())
            if int(payload["norad_cat_id"]) != norad_id:
                raise IngestConflictError("Fixture NORAD ID does not match request")
            if observation_id is not None and int(payload["id"]) != observation_id:
                raise IngestUnavailableError("Fixture has no matching observation")
            return payload
        params: dict[str, int | str] = {
            "norad_cat_id": norad_id,
            "status": "good",
            "limit": limit,
        }
        if observation_id is not None:
            params["id"] = observation_id
        response = httpx.get(config.SATNOGS_OBSERVATIONS_URL, params=params, timeout=20)
        response.raise_for_status()
        if len(response.content) > config.SATNOGS_MAX_RESPONSE_BYTES:
            raise IngestUnavailableError("SatNOGS response exceeds size limit")
        payload = response.json()
    except IngestConflictError:
        raise
    except IngestUnavailableError:
        raise
    except (OSError, ValueError, httpx.HTTPError) as exc:
        raise IngestUnavailableError("SatNOGS observation is unavailable") from exc

    if not isinstance(payload, list) or not payload:
        raise IngestUnavailableError("SatNOGS returned no matching observation")
    return payload[0]


def _result(dataset: Dataset, created: bool) -> IngestResult:
    return IngestResult(
        dataset_id=dataset.id,
        external_id=dataset.external_id,
        object_key=dataset.object_key,
        size_bytes=dataset.size_bytes,
        sha256=dataset.sha256,
        created=created,
    )


def _matching(
    store: ObjectStore,
    bucket: str,
    key: str,
    info: ObjectInfo,
    size_bytes: int,
    sha256: str,
) -> bool:
    if info.size_bytes != size_bytes:
        return False
    stored_checksum = hashlib.sha256(store.get(bucket, key)).hexdigest()
    return hmac.compare_digest(stored_checksum, sha256)


def _lock_ingestion(session: Session, source: str, external_id: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": f"{source}:{external_id}"},
        )


def ingest_satnogs_observation(
    session: Session,
    store: ObjectStore,
    raw: dict,
    norad_id: int,
) -> IngestResult:
    normalized = normalize_observation(raw)
    if normalized["satellite_id"] != norad_id:
        raise IngestConflictError("Observation NORAD ID does not match request")

    external_id = str(normalized["satnogs_observation_id"])
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    checksum = hashlib.sha256(payload).hexdigest()
    key = f"satnogs/{norad_id}/{external_id}.json"
    _lock_ingestion(session, "satnogs", external_id)

    existing = session.scalar(
        select(Dataset).where(Dataset.source == "satnogs", Dataset.external_id == external_id)
    )
    if existing is not None:
        try:
            info = store.stat(config.MINIO_RAW_BUCKET, existing.object_key)
            object_matches = _matching(
                store,
                config.MINIO_RAW_BUCKET,
                existing.object_key,
                info,
                existing.size_bytes,
                existing.sha256,
            )
        except ObjectNotFoundError as exc:
            raise IngestConflictError("Dataset object is missing") from exc
        except Exception as exc:
            raise IngestUnavailableError("Dataset object could not be verified") from exc
        if (
            existing.object_key != key
            or existing.size_bytes != len(payload)
            or not hmac.compare_digest(existing.sha256, checksum)
            or not object_matches
        ):
            raise IngestConflictError("Dataset object checksum or size differs")
        return _result(existing, created=False)

    object_created = False

    try:
        info = store.stat(config.MINIO_RAW_BUCKET, key)
    except ObjectNotFoundError:
        try:
            store.put(config.MINIO_RAW_BUCKET, key, payload, checksum)
            object_created = True
        except (TimeoutError, ReadTimeoutError) as exc:
            try:
                info = store.stat(config.MINIO_RAW_BUCKET, key)
                object_matches = _matching(
                    store, config.MINIO_RAW_BUCKET, key, info, len(payload), checksum
                )
            except ObjectNotFoundError:
                raise IngestUnavailableError("Object upload timed out") from exc
            except Exception as verify_exc:
                raise IngestUnavailableError(
                    "Object could not be verified after upload timeout"
                ) from verify_exc
            if not object_matches:
                raise IngestConflictError("Object differs after upload timeout") from exc
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
            raise IngestConflictError("Existing object checksum or size differs")

    ingested_at = datetime.now(timezone.utc)
    dataset = Dataset(
        source="satnogs",
        external_id=external_id,
        observed_at=normalized["timestamp"],
        size_bytes=len(payload),
        object_key=key,
        sha256=checksum,
        ingested_at=ingested_at,
        satellite_norad_id=norad_id,
    )
    session.add(dataset)
    try:
        session.flush()
        session.add(Observation(dataset_id=dataset.id, ingested_at=ingested_at, **normalized))
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        if object_created:
            try:
                store.delete(config.MINIO_RAW_BUCKET, key)
            except Exception as delete_exc:
                logger.error(
                    "orphan_object bucket=%s key=%s",
                    config.MINIO_RAW_BUCKET,
                    key,
                    exc_info=delete_exc,
                )
                raise OrphanObjectError("Database commit failed and object cleanup failed") from exc
        raise IngestUnavailableError("Database commit failed") from exc

    return _result(dataset, created=True)