from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import tle as tle_module
from app.predict import compute_passes
from app.tle import TLERecord, TLEUnavailableError, get_tle

# ISS TLE, fixed epoch — deterministic fixture, not a live fetch.
ISS_LINE1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9994"
ISS_LINE2 = "2 25544  51.6416 339.0000 0007976  10.0000 350.0000 15.49309620000000"


@pytest.fixture
def iss_tle():
    return TLERecord(
        norad_id=25544,
        name="ISS (ZARYA)",
        line1=ISS_LINE1,
        line2=ISS_LINE2,
        fetched_at=datetime.now(timezone.utc),
        stale=False,
    )


def test_compute_passes_returns_ordered_nonoverlapping_passes(iss_tle):
    passes = compute_passes(
        iss_tle, lat=21.1237, lon=79.0353, elev_m=310, count=5, search_hours=72
    )

    assert 1 <= len(passes) <= 5
    for p in passes:
        assert p["aos"] < p["los"]
        assert 10.0 <= p["max_elevation_deg"] <= 90.0
        assert "->" in p["direction"]
        assert p["tle_stale"] is False

    for earlier, later in zip(passes, passes[1:]):
        assert earlier["los"] <= later["aos"]


def test_compute_passes_respects_count(iss_tle):
    passes = compute_passes(iss_tle, lat=21.1237, lon=79.0353, elev_m=310, count=2)
    assert len(passes) <= 2


def test_get_tle_falls_back_to_cache_when_celestrak_unreachable(monkeypatch):
    tle_module.reset_cache(99999)

    live_record = TLERecord(
        norad_id=99999,
        name="TEST-SAT",
        line1=ISS_LINE1,
        line2=ISS_LINE2,
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=100),
        stale=False,
    )
    tle_module._cache[99999] = live_record

    def fail_fetch(*args, **kwargs):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(tle_module.httpx, "get", fail_fetch)

    result = get_tle(99999)
    assert result.stale is True
    assert result.line1 == ISS_LINE1

    tle_module.reset_cache(99999)


def test_get_tle_raises_when_no_cache_and_unreachable(monkeypatch):
    tle_module.reset_cache(88888)

    def fail_fetch(*args, **kwargs):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(tle_module.httpx, "get", fail_fetch)

    with pytest.raises(TLEUnavailableError):
        get_tle(88888)
