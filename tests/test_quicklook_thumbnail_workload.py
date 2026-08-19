from pathlib import Path

import numpy as np
import pytest
import rasterio

from services.api.aries_api.workloads import sentinel2_quicklook_thumbnail as workload

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


def test_run_decimates_to_expected_thumbnail_size(crop_bytes):
    result = workload.run(crop_bytes)

    assert result.source_width == 128
    assert result.source_height == 128
    assert result.thumbnail_width == 128 // workload.DECIMATION_FACTOR
    assert result.thumbnail_height == 128 // workload.DECIMATION_FACTOR
    assert result.band_count == 2


def test_run_is_deterministic(crop_bytes):
    first = workload.run(crop_bytes)
    second = workload.run(crop_bytes)
    assert first == second


def test_thumbnail_reduction_lands_between_recompress_and_detection_workloads(crop_bytes):
    result = workload.run(crop_bytes)
    output = workload.canonical_result_bytes(result)
    drf = len(crop_bytes) / len(output)

    # Deliberately mid-range: real block-mean decimation + light compression,
    # not a semantic summary -- should not collapse to detection-workload
    # scale (tens to hundreds of x), nor stay near the 1x recompress floor.
    assert 5 < drf < 40


def test_uniform_block_downsamples_to_the_same_uniform_value():
    uniform = np.full((32, 32), 1200, dtype="uint16")
    payload = _two_band_tif(uniform, uniform)

    result = workload.run(payload)
    downsampled = workload._block_mean_downsample(uniform, workload.DECIMATION_FACTOR)

    assert (downsampled == 1200).all()
    assert result.thumbnail_width == 32 // workload.DECIMATION_FACTOR
