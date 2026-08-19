from pathlib import Path

import pytest

from services.api.aries_api.workloads import sentinel2_landcover_classifier as workload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sentinel2_crop_43QHD_128.tif"


@pytest.fixture
def crop_bytes():
    return FIXTURE_PATH.read_bytes()


def test_run_produces_valid_class_distribution(crop_bytes):
    result = workload.run(crop_bytes)

    assert result.width == 128
    assert result.height == 128
    assert result.input_bytes == len(crop_bytes)
    assert set(result.class_pixel_fraction) == set(workload.CLASS_NAMES)
    assert result.dominant_class in workload.CLASS_NAMES
    assert pytest.approx(sum(result.class_pixel_fraction.values()), abs=1e-6) == 1.0


def test_run_is_deterministic(crop_bytes):
    assert workload.run(crop_bytes) == workload.run(crop_bytes)


def test_ground_and_edge_paths_agree_on_classification(crop_bytes):
    # Same model, same input -- the ground (multi-thread) and edge
    # (single-thread constrained) sessions must produce identical
    # predictions. Only their measured timing is expected to differ.
    ground = workload.run(crop_bytes)
    edge = workload.run_edge_constrained(crop_bytes)

    assert ground.class_pixel_fraction == edge.class_pixel_fraction
    assert ground.dominant_class == edge.dominant_class


def test_edge_session_is_actually_single_threaded():
    session = workload._edge_constrained_session()
    options = session.get_session_options()
    assert options.intra_op_num_threads == 1
    assert options.inter_op_num_threads == 1


def test_run_rejects_single_band_payload():
    import numpy as np
    import rasterio

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
