from datetime import datetime, timezone

from sqlmodel import Session

RAW_OBSERVATION = {
    "id": 777001,
    "start": "2026-08-15T02:00:00Z",
    "norad_cat_id": 68635,
    "ground_station": 4869,
    "status": "good",
    "vetted_status": "good",
    "observation_frequency": 401035000,
    "waterfall": "https://example.org/w.png",
    "payload": "https://example.org/a.ogg",
    "demoddata": [{"payload_demod": "https://example.org/frame1"}],
}


def _seed_observation(db_module):
    from app.ingest import ingest_observations
    import app.ingest as ingest_module

    with Session(db_module.engine) as session:
        ingest_module.fetch_recent_observations = lambda norad_id, limit=25: [
            RAW_OBSERVATION
        ]
        ingest_observations(session)


def test_status_reflects_empty_db(app_client):
    client, main_module, db_module = app_client
    db_module.init_db()

    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["observations_ingested_last_24h"] == 0
    assert body["observations_total"] == 0
    assert body["last_successful_ingestion"] is None
    assert body["satellite"]["norad_id"] == 68635


def test_status_reflects_seeded_observations(app_client):
    client, main_module, db_module = app_client
    db_module.init_db()
    _seed_observation(db_module)

    response = client.get("/api/status")
    body = response.json()
    assert body["observations_total"] == 1
    assert body["observations_ingested_last_24h"] == 1
    assert body["last_successful_ingestion"] is not None


def test_observations_endpoint_shape(app_client):
    client, main_module, db_module = app_client
    db_module.init_db()
    _seed_observation(db_module)

    response = client.get("/api/observations")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    obs = body["observations"][0]
    assert obs["satnogs_observation_id"] == 777001
    assert obs["satellite_id"] == 68635
    assert obs["signal_quality"] == "good"
    assert obs["has_decoded_data"] is True
    assert "network.satnogs.org" in obs["satnogs_url"]


def test_dashboard_renders_all_sections_with_empty_state(app_client):
    client, main_module, db_module = app_client
    db_module.init_db()

    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Mission Health" in body
    assert "Upcoming Passes" in body
    assert "Recent Observations" in body
    assert "No observations ingested yet" in body


def test_passes_endpoint_shape(app_client, monkeypatch):
    client, main_module, db_module = app_client
    db_module.init_db()

    from app.tle import TLERecord

    iss_line1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9994"
    iss_line2 = "2 25544  51.6416 339.0000 0007976  10.0000 350.0000 15.49309620000000"
    fixed_tle = TLERecord(
        norad_id=68635,
        name="TEST",
        line1=iss_line1,
        line2=iss_line2,
        fetched_at=datetime.now(timezone.utc),
        stale=False,
    )
    monkeypatch.setattr(main_module, "get_tle", lambda norad_id: fixed_tle)

    response = client.get("/api/passes?count=2")
    assert response.status_code == 200
    body = response.json()
    assert len(body["passes"]) <= 2
    assert body["tle_stale"] is False
    if body["passes"]:
        p = body["passes"][0]
        assert set(p.keys()) == {"aos", "los", "max_elevation_deg", "direction"}


def test_dashboard_renders_seeded_observation_row(app_client):
    client, main_module, db_module = app_client
    db_module.init_db()
    _seed_observation(db_module)

    response = client.get("/")
    body = response.text
    assert "view on SatNOGS" in body
    assert "777001" in body or "network.satnogs.org/observations/777001" in body
