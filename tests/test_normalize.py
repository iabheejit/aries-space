from datetime import timezone

from app.normalize import normalize_observation

FULL_RAW_OBSERVATION = {
    "id": 14790352,
    "start": "2026-08-15T00:28:22Z",
    "end": "2026-08-15T00:35:10Z",
    "ground_station": 4869,
    "norad_cat_id": 68635,
    "payload": "https://example.org/audio.ogg",
    "waterfall": "https://example.org/waterfall.png",
    "vetted_status": "good",
    "status": "good",
    "observation_frequency": 401035000,
    "demoddata": [
        {"payload_demod": "https://example.org/frame1"},
        {"payload_demod": "https://example.org/frame2"},
    ],
}

MINIMAL_RAW_OBSERVATION = {
    "id": 99999999,
    "start": "2026-08-15T01:00:00Z",
    "norad_cat_id": 68635,
    "status": "unknown",
}


def test_normalize_full_observation_maps_all_fields():
    result = normalize_observation(FULL_RAW_OBSERVATION)

    assert result["satnogs_observation_id"] == 14790352
    assert result["satellite_id"] == 68635
    assert result["station_id"] == 4869
    assert result["timestamp"].tzinfo is not None
    assert result["timestamp"].astimezone(timezone.utc).hour == 0
    assert result["frequency"] == 401035000
    assert result["signal_quality"] == "good"
    assert result["waterfall_url"] == "https://example.org/waterfall.png"
    assert result["audio_url"] == "https://example.org/audio.ogg"
    assert "frame1" in result["decoded_data"]


def test_normalize_handles_missing_optional_fields_gracefully():
    result = normalize_observation(MINIMAL_RAW_OBSERVATION)

    assert result["satnogs_observation_id"] == 99999999
    assert result["satellite_id"] == 68635
    assert result["station_id"] is None
    assert result["frequency"] is None
    assert result["waterfall_url"] is None
    assert result["audio_url"] is None
    assert result["decoded_data"] is None
    assert result["signal_quality"] == "unknown"
