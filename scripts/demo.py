import json
import os
import urllib.request
from pathlib import Path

import psycopg

BASE_URL = os.environ.get("ARIES_BASE_URL", "http://127.0.0.1:8000")


def _dotenv_value(name: str) -> str | None:
    path = Path(".env")
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return None


def _required(name: str) -> str:
    value = os.environ.get(name) or _dotenv_value(name)
    if not value or "replace-with-" in value:
        raise RuntimeError(f"{name} must be configured")
    return value


def _request(path: str, method: str = "GET") -> tuple[int, dict]:
    headers = (
        {"Authorization": f"Bearer {_required('API_BEARER_TOKEN')}"}
        if method == "POST"
        else {}
    )
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=b"" if method == "POST" else None,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.load(response)


def main() -> int:
    _request("/api/ingest/satnogs?norad_id=68635&limit=1", method="POST")
    password = _required("POSTGRES_PASSWORD")
    database_url = os.environ.get(
        "DEMO_DATABASE_URL",
        f"postgresql://aries:{password}@127.0.0.1:5432/aries",
    )
    with psycopg.connect(database_url) as connection:
        dataset_id = connection.execute(
            """SELECT d.id FROM datasets d
               JOIN observations o ON o.dataset_id = d.id
               WHERE d.source = 'satnogs'
               ORDER BY d.size_bytes DESC, d.id DESC LIMIT 1"""
        ).fetchone()[0]

    status, pair = _request(
        f"/api/benchmarks?dataset_id={dataset_id}", method="POST"
    )
    assert status == 201
    print(
        json.dumps(
            {
                "status": "ok",
                "pair_id": pair["pair_id"],
                "dataset": pair["dataset"],
                "recommendation": pair["recommendation"],
                "break_even_downlink_inr_per_gb": pair[
                    "break_even_downlink_inr_per_gb"
                ],
                "dashboard_url": f"{BASE_URL}/",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
