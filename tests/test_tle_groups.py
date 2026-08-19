import re

from services.api.aries_api.tle import TLERecord, _parse_tle_text

FIXTURE = """
ISS (ZARYA)
1 25544U 98067A   26228.54791667  .00016717  00000-0  10270-3 0  9004
2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537
NOAA 19
1 33591U 09005A   26228.51787037  .00000075  00000-0  654321-4 0  9999
2 33591  99.1962 245.1234 0014321  45.6789 314.5678 14.12501234567890
"""


def test_group_text_parses_into_records():
    records = _parse_tle_text(FIXTURE, fetched_at=None)
    assert [record.norad_id for record in records] == [25544, 33591]
    assert records[0].name == "ISS (ZARYA)"
    assert records[1].line2.startswith("2 33591")


def test_malformed_blocks_are_discarded():
    records = _parse_tle_text("JUNK\nnot-a-line\nalso-not\n", fetched_at=None)
    assert records == []


def test_group_endpoint_is_cached_and_falls_back_to_stale(monkeypatch):
    from services.api.aries_api import tle

    tle.reset_cache()
    calls = {"count": 0}

    class _Response:
        text = FIXTURE

        def raise_for_status(self):
            return None

    def _get(url, params=None, timeout=None):
        calls["count"] += 1
        if calls["count"] > 1:
            raise tle.httpx.ConnectError("network down")
        return _Response()

    monkeypatch.setattr(tle.httpx, "get", _get)

    first = tle.get_group_tles("resource")
    assert len(first) == 2
    assert calls["count"] == 1
    assert all(record.stale is False for record in first)

    # Force expiry so the next call must re-fetch, and that fetch fails.
    monkeypatch.setattr(tle.config, "TLE_REFRESH_HOURS", 0)
    second = tle.get_group_tles("resource")
    assert calls["count"] == 2
    assert all(record.stale is True for record in second), "fallback must be flagged stale"

    tle.reset_cache()


def test_group_fetch_without_cache_raises(monkeypatch):
    from services.api.aries_api import tle

    tle.reset_cache()

    def _get(url, params=None, timeout=None):
        raise tle.httpx.ConnectError("network down")

    monkeypatch.setattr(tle.httpx, "get", _get)
    try:
        tle.get_group_tles("resource")
    except tle.TLEUnavailableError as exc:
        assert "resource" in str(exc)
    else:
        raise AssertionError("expected TLEUnavailableError")
    tle.reset_cache()


def test_records_carry_valid_tle_line_structure():
    for record in _parse_tle_text(FIXTURE, fetched_at=None):
        assert isinstance(record, TLERecord)
        assert re.match(r"^1 \d{5}", record.line1)
        assert re.match(r"^2 \d{5}", record.line2)
