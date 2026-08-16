import hashlib
import json
from pathlib import Path

from services.api.aries_api.workloads.satnogs_payload_proxy import (
    DETECTOR_VERSION,
    canonical_result_bytes,
    run,
)


def test_payload_proxy_is_deterministic_and_honestly_labeled():
    raw = json.loads((
        Path(__file__).parent / "fixtures" / "satnogs_observation_14790266.json"
    ).read_text())
    payload = json.dumps(
        raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()

    first = run(payload)
    second = run(payload)
    result_bytes = canonical_result_bytes(first)

    assert hashlib.sha256(payload).hexdigest() == (
        "94591a7ab126058ce1c0a0a81c6b7aff35f223ec5f429ccd92a25ee13f17f98f"
    )
    assert first == second
    assert first.detector_version == DETECTOR_VERSION == "payload-proxy-v1"
    assert first.score == 0.48368
    assert first.anomaly is False
    assert first.features["has_demoddata"] is False
    assert first.features["missing_field_ratio"] == 0.6
    assert b"not decoded-frame telemetry anomaly detection" in result_bytes
    assert result_bytes == canonical_result_bytes(second)
