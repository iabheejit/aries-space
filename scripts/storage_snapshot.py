import argparse
import hashlib
import json
import os
from contextlib import closing
from pathlib import Path, PurePosixPath

import psycopg
from minio import Minio

def _dotenv_value(name: str) -> str | None:
    path = Path(".env")
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return None


def _required_setting(name: str) -> str:
    value = os.environ.get(name) or _dotenv_value(name)
    if not value or value.startswith("replace-with-"):
        raise RuntimeError(f"{name} must be configured in the environment or .env")
    return value


POSTGRES_PASSWORD = _required_setting("POSTGRES_PASSWORD")
DATABASE_URL = os.environ.get("SNAPSHOT_DATABASE_URL") or (
    f"postgresql://aries:{POSTGRES_PASSWORD}@127.0.0.1:5432/aries"
)
MINIO_ENDPOINT = os.environ.get("SNAPSHOT_MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = _required_setting("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = _required_setting("MINIO_SECRET_KEY")


def _client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def _safe_path(root: Path, object_key: str) -> Path:
    key = PurePosixPath(object_key)
    if key.is_absolute() or ".." in key.parts:
        raise ValueError(f"unsafe object key: {object_key}")
    return root.joinpath(*key.parts)


def _datasets() -> list[dict]:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT object_key, size_bytes, sha256 FROM datasets ORDER BY object_key"
        ).fetchall()
    return [
        {"bucket": "raw", "object_key": row[0], "size_bytes": row[1], "sha256": row[2]}
        for row in rows
    ]


def _download(client: Minio, bucket: str, key: str) -> bytes:
    with closing(client.get_object(bucket, key)) as response:
        return response.read()


def _verify_payload(payload: bytes, item: dict) -> None:
    if len(payload) != item["size_bytes"]:
        raise ValueError(f"size mismatch for {item['object_key']}")
    if hashlib.sha256(payload).hexdigest() != item["sha256"]:
        raise ValueError(f"checksum mismatch for {item['object_key']}")


def backup(destination: Path) -> None:
    client = _client()
    items = _datasets()
    destination.mkdir(parents=True, exist_ok=True)
    for item in items:
        payload = _download(client, item["bucket"], item["object_key"])
        _verify_payload(payload, item)
        target = _safe_path(destination / item["bucket"], item["object_key"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    (destination / "manifest.json").write_text(
        json.dumps({"version": 1, "objects": items}, indent=2) + "\n"
    )
    print(f"snapshot_objects={len(items)}")
    print("snapshot_integrity=ok")


def restore(source: Path) -> None:
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("version") != 1:
        raise ValueError("unsupported snapshot manifest")
    client = _client()
    for item in manifest["objects"]:
        payload = _safe_path(source / item["bucket"], item["object_key"]).read_bytes()
        _verify_payload(payload, item)
        from io import BytesIO

        if not client.bucket_exists(item["bucket"]):
            client.make_bucket(item["bucket"])
        client.put_object(
            item["bucket"],
            item["object_key"],
            BytesIO(payload),
            len(payload),
            content_type="application/json",
            metadata={"sha256": item["sha256"]},
        )
    print(f"restored_objects={len(manifest['objects'])}")
    verify()


def verify() -> None:
    client = _client()
    items = _datasets()
    for item in items:
        payload = _download(client, item["bucket"], item["object_key"])
        _verify_payload(payload, item)
    print(f"verified_objects={len(items)}")
    print("storage_integrity=ok")


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up and verify Aries dataset objects")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--destination", type=Path, required=True)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--source", type=Path, required=True)
    subparsers.add_parser("verify")
    args = parser.parse_args()

    if args.command == "backup":
        backup(args.destination)
    elif args.command == "restore":
        restore(args.source)
    else:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
