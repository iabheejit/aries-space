from pathlib import Path

import pytest

from services.api.aries_api.workloads import sentinel2_ndvi_summary as workload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sentinel2_crop_43QHD_128.tif"


@pytest.fixture
def crop_bytes():
    return FIXTURE_PATH.read_bytes()


def test_run_computes_plausible_ndvi_summary_from_real_crop(crop_bytes):
    result = workload.run(crop_bytes)

    assert result.width == 128
    assert result.height == 128
    assert result.band_count == 2
    assert result.input_bytes == len(crop_bytes)
    # Real Sentinel-2 L2A pixel data over agricultural cropland (GHRCE/Nagpur
    # region, 2026-06-19, <2% cloud cover) — not synthetic.
    assert result.valid_pixel_fraction == 1.0
    assert -1.0 <= result.ndvi_min <= result.ndvi_mean <= result.ndvi_max <= 1.0
    assert result.ndvi_std >= 0
    assert set(result.ndvi_percentiles) == {"5", "25", "50", "75", "95"}
    assert 0.0 <= result.vegetation_fraction <= 1.0


def test_run_is_deterministic(crop_bytes):
    first = workload.run(crop_bytes)
    second = workload.run(crop_bytes)

    assert first == second


def test_canonical_result_bytes_reduces_input_dramatically(crop_bytes):
    result = workload.run(crop_bytes)
    output = workload.canonical_result_bytes(result)

    assert len(output) < len(crop_bytes) / 10


def test_run_rejects_single_band_payload():
    import numpy as np
    import rasterio

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", dtype="uint16", width=4, height=4, count=1
        ) as dst:
            dst.write(np.zeros((4, 4), dtype="uint16"), 1)
        single_band = bytes(memfile.read())

    with pytest.raises(ValueError, match="at least 2 bands"):
        workload.run(single_band)
