import json
from dataclasses import dataclass

WORKLOAD_SLUG = "satnogs-payload-anomaly-proxy"
DETECTOR_VERSION = "payload-proxy-v1"
ANOMALY_THRESHOLD = 0.65


@dataclass(frozen=True)
class ProxyResult:
    detector_version: str
    score: float
    anomaly: bool
    features: dict[str, float | int | bool]
    input_bytes: int

    def payload(self) -> dict:
        return {
            "workload": WORKLOAD_SLUG,
            "detector_version": self.detector_version,
            "score": self.score,
            "anomaly": self.anomaly,
            "features": self.features,
            "input_bytes": self.input_bytes,
            "limitations": "Payload/metadata proxy; not decoded-frame telemetry anomaly detection.",
        }


def run(payload: bytes) -> ProxyResult:
    raw = json.loads(payload)
    if not isinstance(raw, dict):
        raise ValueError("SatNOGS payload must be a JSON object")

    has_demoddata = bool(raw.get("demoddata"))
    has_waterfall = bool(raw.get("waterfall"))
    has_audio = bool(raw.get("archive_url") or raw.get("audio_url"))
    has_frequency = raw.get("frequency") is not None
    has_station = raw.get("station_id") is not None or raw.get("ground_station") is not None
    payload_size = len(payload)

    missing_ratio = 1 - sum(
        (has_demoddata, has_waterfall, has_audio, has_frequency, has_station)
    ) / 5
    size_pressure = min(payload_size / 20_000, 1.0)
    score = round(0.8 * missing_ratio + 0.2 * size_pressure, 6)
    features: dict[str, float | int | bool] = {
        "payload_bytes": payload_size,
        "has_demoddata": has_demoddata,
        "has_waterfall": has_waterfall,
        "has_audio": has_audio,
        "has_frequency": has_frequency,
        "has_station": has_station,
        "missing_field_ratio": round(missing_ratio, 6),
    }
    return ProxyResult(
        detector_version=DETECTOR_VERSION,
        score=score,
        anomaly=score >= ANOMALY_THRESHOLD,
        features=features,
        input_bytes=payload_size,
    )


def canonical_result_bytes(result: ProxyResult) -> bytes:
    return json.dumps(
        result.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
