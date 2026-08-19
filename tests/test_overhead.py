from datetime import datetime, timedelta, timezone

import pytest

from services.api.aries_api import config, overhead
from services.api.aries_api.tle import TLERecord

# Real ISS (ZARYA) TLE, epoch 2026-08-16. Used as a fixed, known-good element
# set so these assertions test propagation, not a live network response.
ISS_LINE1 = "1 25544U 98067A   26228.54791667  .00016717  00000-0  10270-3 0  9004"
ISS_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"

FIXED_EPOCH = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)


def _record(norad_id: int = 25544, name: str = "ISS (ZARYA)") -> TLERecord:
    return TLERecord(norad_id, name, ISS_LINE1, ISS_LINE2, FIXED_EPOCH)


def test_footprint_radius_grows_with_altitude():
    low = overhead._footprint_radius_km(400)
    high = overhead._footprint_radius_km(35786)
    assert 0 < low < high
    # A geostationary satellite sees roughly a third of the globe; its
    # footprint radius must be several thousand km larger than a LEO pass.
    assert high > 8000
    assert overhead._footprint_radius_km(0) == 0.0


def test_orbital_elements_are_parsed_from_the_real_tle():
    assert overhead._inclination_deg(ISS_LINE2) == pytest.approx(51.6416)
    # 15.72 revs/day -> ~92 minute orbit.
    assert overhead._period_minutes(ISS_LINE2) == pytest.approx(91.6, abs=0.5)


def test_malformed_tle_line_yields_no_elements():
    assert overhead._inclination_deg("not a tle") is None
    assert overhead._period_minutes("not a tle") is None


def test_satellite_state_is_physically_plausible():
    state = overhead.satellite_states([_record()], now=FIXED_EPOCH)[0]
    assert state["norad_id"] == 25544
    assert -90 <= state["lat"] <= 90
    assert -180 <= state["lon"] <= 180
    # ISS orbits at roughly 400-430 km travelling near 7.7 km/s.
    assert 350 < state["altitude_km"] < 460
    assert 7.0 < state["velocity_km_s"] < 8.0
    assert -90 <= state["elevation_deg"] <= 90
    assert state["footprint_radius_km"] > 0
    assert state["inclination_deg"] == pytest.approx(51.6416)


def test_position_actually_changes_over_time():
    early = overhead.satellite_states([_record()], now=FIXED_EPOCH)[0]
    later = overhead.satellite_states(
        [_record()], now=FIXED_EPOCH + timedelta(minutes=10)
    )[0]
    moved = abs(early["lat"] - later["lat"]) + abs(early["lon"] - later["lon"])
    assert moved > 1.0, "10 minutes of propagation must move the sub-point"


def test_visibility_follows_the_elevation_threshold():
    above = overhead.satellite_states([_record()], now=FIXED_EPOCH, min_elevation_deg=-90)[0]
    below = overhead.satellite_states([_record()], now=FIXED_EPOCH, min_elevation_deg=90)[0]
    assert above["visible"] is True
    assert below["visible"] is False


def test_unpropagatable_tle_is_skipped_not_fatal():
    broken = TLERecord(1, "BROKEN", "1 garbage", "2 garbage", FIXED_EPOCH)
    states = overhead.satellite_states([broken, _record()], now=FIXED_EPOCH)
    assert [state["norad_id"] for state in states] == [25544]


def test_states_are_sorted_by_elevation_descending():
    records = [_record(), _record(norad_id=25545, name="COPY")]
    states = overhead.satellite_states(records, now=FIXED_EPOCH)
    elevations = [state["elevation_deg"] for state in states]
    assert elevations == sorted(elevations, reverse=True)


def test_max_satellites_cap_is_enforced(monkeypatch):
    monkeypatch.setattr(config, "OVERHEAD_MAX_SATELLITES", 2)
    records = [_record(norad_id=25544 + index) for index in range(5)]
    assert len(overhead.satellite_states(records, now=FIXED_EPOCH)) == 2


def test_ground_track_spans_the_requested_window():
    track = overhead.ground_track(_record(), minutes=90, step_seconds=60, now=FIXED_EPOCH)
    assert len(track) == 91
    assert all(-180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in track)
    # A 90-minute ISS window is a full orbit, so the track must traverse a
    # wide latitude band rather than sit still.
    latitudes = [lat for _, lat in track]
    assert max(latitudes) - min(latitudes) > 60


def test_subsolar_point_matches_known_solstice_declination():
    # Northern summer solstice: subsolar latitude must be near +23.44 deg
    # (the formula's amplitude), independent of time of day.
    solstice = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
    point = overhead.subsolar_point(solstice)
    assert point["lat"] == pytest.approx(23.44, abs=0.5)
    assert -90 <= point["lat"] <= 90
    assert -180 <= point["lon"] <= 180


def test_subsolar_longitude_tracks_local_noon():
    # At 00:00 UTC the subsolar point is near the 180th meridian (it's noon
    # there); at 12:00 UTC it's near the prime meridian.
    midnight_utc = overhead.subsolar_point(datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc))
    noon_utc = overhead.subsolar_point(datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc))
    assert abs(midnight_utc["lon"]) > 150
    assert abs(noon_utc["lon"]) < 5


def test_ground_track_for_uses_the_cached_group_first(monkeypatch):
    calls = {"live_fetch": 0}
    monkeypatch.setattr(overhead, "get_group_tles", lambda group: [_record()])

    def _live(_norad_id):
        calls["live_fetch"] += 1
        return _record()

    monkeypatch.setattr(overhead, "get_tle", _live)

    track = overhead.ground_track_for(25544, minutes=10, now=FIXED_EPOCH)

    assert track
    assert calls["live_fetch"] == 0  # found in the cached group; no extra fetch


def test_ground_track_for_falls_back_to_a_live_fetch(monkeypatch):
    monkeypatch.setattr(overhead, "get_group_tles", lambda group: [])
    monkeypatch.setattr(overhead, "get_tle", lambda norad_id: _record(norad_id=norad_id))

    track = overhead.ground_track_for(25544, minutes=10, now=FIXED_EPOCH)

    assert track


def test_ground_track_for_returns_empty_when_truly_unavailable(monkeypatch):
    from services.api.aries_api.tle import TLEUnavailableError

    monkeypatch.setattr(overhead, "get_group_tles", lambda group: [])

    def _unavailable(_norad_id):
        raise TLEUnavailableError("no tle")

    monkeypatch.setattr(overhead, "get_tle", _unavailable)

    assert overhead.ground_track_for(99999, minutes=10, now=FIXED_EPOCH) == []


def test_build_snapshot_uses_real_sources(monkeypatch):
    tracked = _record(norad_id=config.NORAD_ID, name="CANVAS")
    others = [_record(norad_id=40000, name="OTHER")]
    monkeypatch.setattr(overhead, "get_group_tles", lambda group: others)
    monkeypatch.setattr(overhead, "get_tle", lambda norad_id: tracked)

    snapshot = overhead.build_snapshot(now=FIXED_EPOCH)

    assert snapshot["total_count"] == 2
    assert snapshot["tracked"]["norad_id"] == config.NORAD_ID
    assert snapshot["ground_track"], "tracked satellite must have a real ground track"
    assert snapshot["station"]["lat"] == config.STATION_LAT
    assert "SGP4" in snapshot["source"]
    assert snapshot["visible_count"] == sum(
        1 for state in snapshot["satellites"] if state["visible"]
    )
    assert -90 <= snapshot["subsolar"]["lat"] <= 90
    assert -180 <= snapshot["subsolar"]["lon"] <= 180


def test_build_snapshot_survives_a_missing_tracked_tle(monkeypatch):
    from services.api.aries_api.tle import TLEUnavailableError

    def _unavailable(_norad_id):
        raise TLEUnavailableError("no tle")

    monkeypatch.setattr(overhead, "get_group_tles", lambda group: [_record(norad_id=40000)])
    monkeypatch.setattr(overhead, "get_tle", _unavailable)

    snapshot = overhead.build_snapshot(now=FIXED_EPOCH)

    assert snapshot["tracked"] is None
    assert snapshot["ground_track"] == []
    assert snapshot["total_count"] == 1
