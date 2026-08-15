import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

import psycopg
from minio import Minio

TIMEOUT_SECONDS = 180
BASE_URL = os.environ.get("ARIES_BASE_URL", "http://127.0.0.1:8000")


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


API_BEARER_TOKEN = _required_setting("API_BEARER_TOKEN")
POSTGRES_PASSWORD = _required_setting("POSTGRES_PASSWORD")
MINIO_ACCESS_KEY = _required_setting("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = _required_setting("MINIO_SECRET_KEY")
SQLALCHEMY_DATABASE_URL = os.environ.get("SMOKE_DATABASE_URL") or (
    f"postgresql+psycopg://aries:{POSTGRES_PASSWORD}@127.0.0.1:5432/aries"
)
PSYCOPG_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace(
    "postgresql+psycopg://", "postgresql://", 1
)


def _json_request(path: str, method: str = "GET") -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {API_BEARER_TOKEN}"} if method == "POST" else {}
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=b"" if method == "POST" else None,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.load(response)


def _wait_ready(deadline: float) -> None:
    last_error = "not started"
    while time.monotonic() < deadline:
        try:
            status, body = _json_request("/health/ready")
            if status == 200 and body == {"status": "ready"}:
                return
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise TimeoutError(f"readiness timed out: {last_error}")


def _migration_round_trip() -> None:
    admin_url = PSYCOPG_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    test_database = "aries_migration_test"
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{test_database}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{test_database}"')
    environment = {
        **os.environ,
        "DATABASE_URL": SQLALCHEMY_DATABASE_URL.rsplit("/", 1)[0]
        + f"/{test_database}",
        "MINIO_ACCESS_KEY": MINIO_ACCESS_KEY,
        "MINIO_SECRET_KEY": MINIO_SECRET_KEY,
        "API_BEARER_TOKEN": API_BEARER_TOKEN,
    }
    try:
        for command in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
            subprocess.run(
                [sys.executable, "-m", "alembic", *command],
                check=True,
                env=environment,
                timeout=30,
                stdout=subprocess.DEVNULL,
            )
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{test_database}" WITH (FORCE)')


def main() -> int:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    _wait_ready(deadline)
    assert _json_request("/health/live") == (200, {"status": "alive"})
    _migration_round_trip()

    created_status, created = _json_request(
        "/api/ingest/satnogs?norad_id=68635&limit=1", method="POST"
    )
    repeated_status, repeated = _json_request(
        f"/api/ingest/satnogs?norad_id=68635&observation_id={created['external_id']}",
        method="POST",
    )
    assert created_status in {200, 201}
    assert repeated_status == 200
    assert created == repeated
    benchmark_status, benchmark = _json_request(
        f"/api/benchmarks?dataset_id={created['dataset_id']}", method="POST"
    )
    assert benchmark_status == 201
    assert len(benchmark["runs"]) == 2
    assert {run["power_source"] for run in benchmark["runs"]} == {
        "estimated",
        "simulated",
    }

    with psycopg.connect(PSYCOPG_DATABASE_URL) as connection:
        migration = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        dataset = connection.execute(
            """SELECT count(*), min(object_key), min(sha256), min(size_bytes)
               FROM datasets WHERE source = 'satnogs' AND external_id = %s""",
            (created["external_id"],),
        ).fetchone()
        observation_count = connection.execute(
            "SELECT count(*) FROM observations WHERE satnogs_observation_id = %s",
            (int(created["external_id"]),),
        ).fetchone()
    assert migration == "0002_benchmark_kernel"
    assert dataset[0] == observation_count[0] == 1
    assert dataset[1:] == (created["object_key"], created["sha256"], created["size_bytes"])

    minio = Minio(
        "127.0.0.1:9000",
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    assert sorted(bucket.name for bucket in minio.list_buckets()) == ["processed", "raw", "results"]
    assert list(minio.list_objects("processed", recursive=True)) == []
    raw_objects = list(minio.list_objects("raw", recursive=True))
    assert created["object_key"] in {item.object_name for item in raw_objects}
    result_objects = list(minio.list_objects("results", recursive=True))
    expected_result_keys = {run["result_object_key"] for run in benchmark["runs"]}
    assert expected_result_keys <= {item.object_name for item in result_objects}
    with closing(minio.get_object("raw", created["object_key"])) as response:
        payload = response.read()
    assert len(payload) == created["size_bytes"]
    assert hashlib.sha256(payload).hexdigest() == created["sha256"]

    subprocess.run(
        ["docker", "compose", "up", "--detach", "--force-recreate", "app"],
        check=True,
        timeout=max(1, int(deadline - time.monotonic())),
        stdout=subprocess.DEVNULL,
    )
    _wait_ready(deadline)
    after_status, after = _json_request(
        f"/api/ingest/satnogs?norad_id=68635&observation_id={created['external_id']}",
        method="POST",
    )
    assert after_status == 200
    assert after == created
    latest_status, latest = _json_request(
        "/api/benchmarks/latest?workload=satnogs-payload-anomaly-proxy"
    )
    assert latest_status == 200
    assert latest["pair_id"] == benchmark["pair_id"]
    print(
        json.dumps(
            {
                "status": "ok",
                "migration": migration,
                "benchmark_pair_id": benchmark["pair_id"],
                **created,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())