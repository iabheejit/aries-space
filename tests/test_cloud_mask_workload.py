from pathlib import Path

import numpy as np
import pytest
import rasterio

from services.api.aries_api.workloads import cloud_mask as workload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sentinel2_crop_43QHD_128.tif"


@pytest.fixture
def crop_bytes():
    return FIXTURE_PATH.read_bytes()


def _two_band_tif(red: np.ndarray, nir: np.ndarray) -> bytes:
    height, width = red.shape
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", dtype="uint16", width=width, height=height, count=2) as dst:
            dst.write(red.astype("uint16"), 1)
            dst.write(nir.astype("uint16"), 2)
        return bytes(memfile.read())


def test_run_computes_plausible_cloud_fraction_from_real_crop(crop_bytes):
    result = workload.run(crop_bytes)

    assert result.width == 128
    assert result.height == 128
    assert result.input_bytes == len(crop_bytes)
    assert 0.0 <= result.cloud_fraction <= 1.0
    assert round(result.cloud_fraction + result.clear_fraction, 6) == 1.0
    assert set(result.quadrant_cloud_fraction) == {"nw", "ne", "sw", "se"}


def test_run_is_deterministic(crop_bytes):
    assert workload.run(crop_bytes) == workload.run(crop_bytes)


def test_all_bright_scene_is_fully_cloudy():
    bright = np.full((32, 32), 5000, dtype="uint16")
    payload = _two_band_tif(bright, bright)

    result = workload.run(payload)

    assert result.cloud_fraction == 1.0
    assert result.clear_fraction == 0.0


def test_dark_scene_is_fully_clear():
    dark = np.full((32, 32), 300, dtype="uint16")
    payload = _two_band_tif(dark, dark)

    result = workload.run(payload)

    assert result.cloud_fraction == 0.0
    assert result.clear_fraction == 1.0


def test_run_rejects_single_band_payload():
    single = np.full((16, 16), 500, dtype="uint16")
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", dtype="uint16", width=16, height=16, count=1) as dst:
            dst.write(single, 1)
        payload = bytes(memfile.read())

    with pytest.raises(ValueError, match="at least 2 bands"):
        workload.run(payload)


def test_canonical_result_bytes_reduces_input(crop_bytes):
    result = workload.run(crop_bytes)
    output = workload.canonical_result_bytes(result)

    assert len(output) < len(crop_bytes) / 5
