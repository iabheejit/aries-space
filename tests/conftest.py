import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Fresh FastAPI app + isolated SQLite DB per test, scheduler disabled
    (tests drive ingestion/prediction explicitly, not on a timer).
    """
    db_path = tmp_path / "test_missionops.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    import app.config as config_module
    import app.db as db_module
    import app.main as main_module

    importlib.reload(config_module)
    importlib.reload(db_module)
    importlib.reload(main_module)

    monkeypatch.setattr(main_module, "start_scheduler", lambda: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)

    with TestClient(main_module.app) as client:
        yield client, main_module, db_module
