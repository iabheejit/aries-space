import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.api.aries_api import config, main
from services.api.aries_api.models import Base
from services.api.aries_api.storage import ObjectInfo, ObjectNotFoundError
from services.api.aries_api.tle import TLERecord


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.ready = True

    def ensure_buckets(self):
        return None

    def check(self):
        if not self.ready:
            raise RuntimeError("secret=minio-password")

    def stat(self, bucket, key):
        try:
            payload, checksum = self.objects[(bucket, key)]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc
        return ObjectInfo(len(payload), checksum)

    def put(self, bucket, key, payload, checksum):
        self.objects[(bucket, key)] = (payload, checksum)

    def delete(self, bucket, key):
        self.objects.pop((bucket, key), None)

    def get(self, bucket, key):
        try:
            return self.objects[(bucket, key)][0]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc


@pytest.fixture
def api(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    store = MemoryStore()
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "satnogs_observation_14790266.json").read_text()
    )

    def session_override():
        with sessions() as session:
            yield session

    fixed_tle = TLERecord(
        68635,
        "TEST",
        "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9994",
        "2 25544  51.6416 339.0000 0007976  10.0000 350.0000 15.49309620000000",
        datetime.now(timezone.utc),
    )
    main.app.dependency_overrides[main.get_session] = session_override
    main.app.dependency_overrides[main.get_store] = lambda: store
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main, "get_tle", lambda _: fixed_tle)
    monkeypatch.setattr(main, "fetch_observation", lambda *_: raw)
    monkeypatch.setattr(main, "check_database", lambda: None)
    monkeypatch.setattr(main.config, "SCHEDULER_ENABLED", False)
    with TestClient(main.app) as client:
        yield client, store, sessions
    main.app.dependency_overrides.clear()


def test_liveness_touches_neither_dependency(api, monkeypatch):
    client, store, _ = api
    monkeypatch.setattr(main, "check_database", lambda: (_ for _ in ()).throw(AssertionError()))
    store.check = lambda: (_ for _ in ()).throw(AssertionError())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_checks_both_dependencies(api):
    client, _, _ = api
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.parametrize("dependency", ["postgresql", "minio"])
def test_readiness_failure_is_sanitized_and_logged(api, monkeypatch, caplog, dependency):
    client, store, _ = api
    if dependency == "postgresql":
        monkeypatch.setattr(
            main,
            "check_database",
            lambda: (_ for _ in ()).throw(RuntimeError("password=database-secret")),
        )
    else:
        store.ready = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service is not ready"}
    assert dependency in caplog.text
    assert "password=" not in caplog.text
    assert "secret=" not in caplog.text


def test_readiness_hanging_dependency_is_bounded(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(main.config, "READINESS_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(main, "check_database", lambda: time.sleep(0.05))

    started = time.monotonic()
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service is not ready"}
    assert time.monotonic() - started < 0.04


def test_missionops_routes_and_dashboard_contract(api):
    client, _, _ = api

    status = client.get("/api/status")
    observations = client.get("/api/observations?limit=25&offset=0")
    passes = client.get("/api/passes?count=2")
    dashboard = client.get("/")

    assert status.status_code == observations.status_code == passes.status_code == dashboard.status_code == 200
    assert set(status.json()) == {
        "satellite",
        "station",
        "observations_ingested_last_24h",
        "observations_total",
        "last_successful_ingestion",
        "last_ingestion_error",
    }
    assert status.json()["observations_total"] == 0
    assert set(observations.json()) == {"total", "limit", "offset", "observations"}
    assert set(passes.json()) == {"satellite", "station", "tle_stale", "tle_fetched_at", "passes"}
    for name in ("Ground Segment", "Mission Health", "Upcoming Passes", "Recent Observations"):
        assert name in dashboard.text
    assert "No observations ingested yet" in dashboard.text
    assert client.get("/api/passes?count=0").status_code == 422
    assert client.get("/api/observations?limit=101").status_code == 422


def test_dashboard_renders_empty_passes_and_stale_tle(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(main, "compute_passes", lambda *_: [])
    monkeypatch.setattr(main.get_tle(config.NORAD_ID), "stale", True)

    response = client.get("/")

    assert response.status_code == 200
    assert "No upcoming passes computed yet" in response.text
    assert "cached (stale) TLE" in response.text


def test_dashboard_degrades_cleanly_when_postgresql_fails(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(
        main,
        "compute_status",
        lambda _: (_ for _ in ()).throw(SQLAlchemyError("database-secret")),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "Mission storage is temporarily unavailable" in response.text
    assert "database-secret" not in response.text


def test_ingest_returns_created_then_idempotent_and_updates_routes(api):
    client, store, sessions = api
    headers = {"Authorization": f"Bearer {main.config.API_BEARER_TOKEN}"}

    created = client.post("/api/ingest/satnogs?norad_id=68635&limit=1", headers=headers)
    repeated = client.post(
        "/api/ingest/satnogs?norad_id=68635&observation_id=14790266",
        headers=headers,
    )

    assert created.status_code == 201
    assert repeated.status_code == 200
    assert created.json() == repeated.json()
    assert set(created.json()) == {"dataset_id", "external_id", "object_key", "size_bytes", "sha256"}
    assert len(store.objects) == 1
    assert client.get("/api/status").json()["observations_total"] == 1
    observation = client.get("/api/observations").json()["observations"][0]
    assert observation["satnogs_observation_id"] == 14790266
    assert observation["has_decoded_data"] is False
    dashboard = client.get("/")
    assert "view on SatNOGS" in dashboard.text
    assert "14790266" in dashboard.text


def test_ingest_requires_bearer_token(api):
    client, _, _ = api

    missing = client.post("/api/ingest/satnogs?norad_id=68635&limit=1")
    invalid = client.post(
        "/api/ingest/satnogs?norad_id=68635&limit=1",
        headers={"Authorization": "Bearer invalid"},
    )

    assert missing.status_code == invalid.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"


def test_ingest_minio_stat_outage_returns_503(api):
    client, store, _ = api
    headers = {"Authorization": f"Bearer {main.config.API_BEARER_TOKEN}"}
    assert client.post(
        "/api/ingest/satnogs?norad_id=68635&limit=1", headers=headers
    ).status_code == 201
    store.stat = lambda *_: (_ for _ in ()).throw(RuntimeError("minio unavailable"))

    response = client.post(
        "/api/ingest/satnogs?norad_id=68635&observation_id=14790266",
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Dataset object could not be verified"}