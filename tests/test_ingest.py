import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app import ingest
from app.models import Observation

RAW_OBSERVATION = {
    "id": 555001,
    "start": "2026-08-15T02:00:00Z",
    "norad_cat_id": 68635,
    "ground_station": 1234,
    "status": "good",
    "vetted_status": "good",
    "observation_frequency": 401035000,
    "waterfall": "https://example.org/w.png",
    "payload": "https://example.org/a.ogg",
    "demoddata": [],
}


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_ingest_stores_new_observation_and_skips_duplicates(session, monkeypatch):
    monkeypatch.setattr(
        ingest, "fetch_recent_observations", lambda norad_id, limit=25: [RAW_OBSERVATION]
    )

    stored_first = ingest.ingest_observations(session)
    stored_second = ingest.ingest_observations(session)

    assert stored_first == 1
    assert stored_second == 0
    assert len(session.exec(select(Observation)).all()) == 1
    assert ingest.get_last_successful_ingestion() is not None
    assert ingest.get_last_ingestion_error() is None


def test_ingest_failure_leaves_last_successful_ingestion_unchanged(session, monkeypatch):
    monkeypatch.setattr(
        ingest, "fetch_recent_observations", lambda norad_id, limit=25: [RAW_OBSERVATION]
    )
    ingest.ingest_observations(session)
    first_success = ingest.get_last_successful_ingestion()

    def fail(*args, **kwargs):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(ingest, "fetch_recent_observations", fail)

    stored = ingest.ingest_observations(session)

    assert stored == 0
    assert ingest.get_last_successful_ingestion() == first_success
    assert ingest.get_last_ingestion_error() is not None
    assert len(session.exec(select(Observation)).all()) == 1
