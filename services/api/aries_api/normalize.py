import json
from datetime import datetime
from typing import Any, TypedDict


class NormalizedObservation(TypedDict):
    satnogs_observation_id: int
    satellite_id: int
    station_id: int | None
    timestamp: datetime
    frequency: int | None
    signal_quality: str | None
    waterfall_url: str | None
    audio_url: str | None
    decoded_data: str | None


def normalize_observation(raw: dict[str, Any]) -> NormalizedObservation:
    demoddata = raw.get("demoddata") or []
    return NormalizedObservation(
        satnogs_observation_id=int(raw["id"]),
        satellite_id=int(raw["norad_cat_id"]),
        station_id=raw.get("ground_station"),
        timestamp=datetime.fromisoformat(raw["start"].replace("Z", "+00:00")),
        frequency=raw.get("observation_frequency") or raw.get("center_frequency"),
        signal_quality=raw.get("vetted_status") or raw.get("status"),
        waterfall_url=raw.get("waterfall"),
        audio_url=raw.get("payload"),
        decoded_data=json.dumps(demoddata) if demoddata else None,
    )