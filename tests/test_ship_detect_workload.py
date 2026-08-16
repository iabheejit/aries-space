from pathlib import Path

import numpy as np
import pytest
import rasterio

from services.api.aries_api.workloads import ship_detect as workload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sentinel2_crop_43QBA_coastal_128.tif"


@pytest.fixture
def crop_bytes():
    return FIXTURE_PATH.read_bytes()


def _single_band_tif(values: np.ndarray) -> bytes:
    height, width = values.shape
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", dtype="uint16", width=width, height=height, count=1) as dst:
            dst.write(values.astype("uint16"), 1)
        return bytes(memfile.read())


def test_run_counts_bright_clusters_from_real_crop(crop_bytes):
    result = workload.run(crop_bytes)

    assert result.width == 128
    assert result.height == 128
    assert result.input_bytes == len(crop_bytes)
    assert result.bright_pixel_count > 0
    assert 0.0 <= result.bright_pixel_fraction <= 1.0
    assert len(result.candidate_cells) > 0
    for cell in result.candidate_cells:
        assert cell["bright_pixel_count"] > 0


def test_run_is_deterministic(crop_bytes):
    assert workload.run(crop_bytes) == workload.run(crop_bytes)


def test_uniform_scene_reports_zero_bright_pixels():
    uniform = np.full((64, 64), 500, dtype="uint16")
    payload = _single_band_tif(uniform)

    result = workload.run(payload)

    assert result.bright_pixel_count == 0
    assert result.bright_pixel_fraction == 0.0
    assert result.candidate_cells == []


def test_isolated_bright_spot_is_detected():
    scene = np.full((64, 64), 500, dtype="uint16")
    scene[10:12, 10:12] = 9000
    payload = _single_band_tif(scene)

    result = workload.run(payload)

    assert result.bright_pixel_count == 4
    assert len(result.candidate_cells) >= 1


def test_canonical_result_bytes_reduces_input(crop_bytes):
    result = workload.run(crop_bytes)
    output = workload.canonical_result_bytes(result)

    assert len(output) < len(crop_bytes) / 5
