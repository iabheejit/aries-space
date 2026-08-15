import json
from datetime import datetime
from typing import Any, Dict, Optional, TypedDict


class NormalizedObservation(TypedDict):
    satnogs_observation_id: int
    satellite_id: int
    station_id: Optional[int]
    timestamp: datetime
    frequency: Optional[int]
    signal_quality: Optional[str]
    waterfall_url: Optional[str]
    audio_url: Optional[str]
    decoded_data: Optional[str]


def normalize_observation(raw: Dict[str, Any]) -> NormalizedObservation:
    """Map a raw SatNOGS /api/observations/ record into the structured
    schema. Only surfaces fields SatNOGS already provides — no new
    decoding logic. Missing optional fields become None rather than
    raising, since coverage varies by satellite/station.
    """
    demoddata = raw.get("demoddata") or []
    decoded_data = json.dumps(demoddata) if demoddata else None

    return NormalizedObservation(
        satnogs_observation_id=raw["id"],
        satellite_id=raw["norad_cat_id"],
        station_id=raw.get("ground_station"),
        timestamp=datetime.fromisoformat(raw["start"].replace("Z", "+00:00")),
        frequency=raw.get("observation_frequency") or raw.get("center_frequency"),
        signal_quality=raw.get("vetted_status") or raw.get("status"),
        waterfall_url=raw.get("waterfall"),
        audio_url=raw.get("payload"),
        decoded_data=decoded_data,
    )
