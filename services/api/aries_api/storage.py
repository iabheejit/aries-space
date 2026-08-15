from dataclasses import dataclass
from io import BytesIO

from minio import Minio
from minio.error import S3Error
from urllib3 import Timeout

from services.api.aries_api import config


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    sha256: str | None


class ObjectNotFoundError(Exception):
    pass


class ObjectStore:
    def __init__(self, client: Minio | None = None) -> None:
        self.client = client or Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
            http_client=__import__("urllib3").PoolManager(timeout=Timeout(total=2.0)),
        )

    def ensure_buckets(self) -> None:
        for bucket in config.MINIO_BUCKETS:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)

    def check(self) -> None:
        self.client.bucket_exists(config.MINIO_RAW_BUCKET)

    def put(self, bucket: str, key: str, payload: bytes, sha256: str) -> None:
        self.client.put_object(
            bucket,
            key,
            BytesIO(payload),
            len(payload),
            content_type="application/json",
            metadata={"sha256": sha256},
        )

    def stat(self, bucket: str, key: str) -> ObjectInfo:
        try:
            stat = self.client.stat_object(bucket, key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise ObjectNotFoundError(key) from exc
            raise
        metadata = stat.metadata or {}
        checksum = metadata.get("x-amz-meta-sha256") or metadata.get("sha256")
        return ObjectInfo(size_bytes=stat.size, sha256=checksum)

    def delete(self, bucket: str, key: str) -> None:
        self.client.remove_object(bucket, key)

    def get(self, bucket: str, key: str) -> bytes:
        response = self.client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()