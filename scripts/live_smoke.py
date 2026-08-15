import json
import os
import urllib.request
from pathlib import Path


def _token() -> str:
    if value := os.environ.get("API_BEARER_TOKEN"):
        if "replace-with-" not in value:
            return value
        raise RuntimeError("API_BEARER_TOKEN contains a placeholder value")
    path = Path(".env")
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.startswith("API_BEARER_TOKEN="):
                value = line.split("=", 1)[1].strip()
                if value and not value.startswith("replace-with-"):
                    return value
    raise RuntimeError("API_BEARER_TOKEN must be configured in the environment or .env")


def _post(path: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        data=b"",
        headers={"Authorization": f"Bearer {_token()}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.load(response)


def main() -> int:
    first_status, first = _post("/api/ingest/satnogs?norad_id=68635&limit=1")
    second_status, second = _post(
        f"/api/ingest/satnogs?norad_id=68635&observation_id={first['external_id']}"
    )
    assert first_status in {200, 201}
    assert second_status == 200
    assert first == second
    print(json.dumps({"status": "ok", **first}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())