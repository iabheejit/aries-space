import importlib

import pytest

import services.api.aries_api.config as config


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("STATION_LAT", "91"),
        ("STATION_LAT", "nan"),
        ("STATION_LON", "-181"),
        ("STATION_ELEV_M", "inf"),
        ("TLE_REFRESH_HOURS", "0"),
        ("OBS_POLL_MINUTES", "4"),
        ("DATABASE_URL", "sqlite:///missionops.db"),
        ("DATABASE_URL", "postgresql+psycopg://aries:replace-with-password@postgres/aries"),
        ("SCHEDULER_ENABLED", "sometimes"),
    ],
)
def test_invalid_environment_fails_with_variable_name(monkeypatch, name, value):
    original = getattr(config, name)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name) as error:
        importlib.reload(config)

    assert type(error.value).__name__ == "ConfigurationError"

    monkeypatch.setenv(name, str(original))
    importlib.reload(config)


def test_default_configuration_targets_canvas_and_approximate_ghrce():
    assert config.NORAD_ID == 68635
    assert config.SATELLITE_NAME == "CANVAS"
    assert config.STATION_NAME == "GHRCE campus (approx.)"
    assert config.STATION_LAT == pytest.approx(21.1052484)
    assert config.STATION_LON == pytest.approx(79.0034903)
    assert config.SCHEDULER_ENABLED is True


def test_scheduler_can_be_disabled(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    importlib.reload(config)

    assert config.SCHEDULER_ENABLED is False

    monkeypatch.delenv("SCHEDULER_ENABLED")
    importlib.reload(config)