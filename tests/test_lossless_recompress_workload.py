import zlib
from pathlib import Path

import pytest

from services.api.aries_api.workloads import sentinel2_lossless_recompress as workload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sentinel2_crop_43QHD_128.tif"


@pytest.fixture
def crop_bytes():
    return FIXTURE_PATH.read_bytes()


def test_run_produces_smaller_but_not_tiny_output(crop_bytes):
    result = workload.run(crop_bytes)
    output = workload.canonical_result_bytes(result)

    assert result.width == 128
    assert result.height == 128
    assert result.band_count == 2
    assert result.input_bytes == len(crop_bytes)
    assert len(output) < result.raw_pixel_bytes
    # This is a near-1x placement-frontier workload by design -- it must NOT
    # collapse to a tiny summary the way the detection workloads do.
    assert len(output) > result.raw_pixel_bytes / 3


def test_run_is_deterministic(crop_bytes):
    first = workload.run(crop_bytes)
    second = workload.run(crop_bytes)
    assert first == second
    assert first.compressed_sha256 == second.compressed_sha256


def test_output_is_genuinely_decompressible_to_original_pixels(crop_bytes):
    result = workload.run(crop_bytes)
    output = workload.canonical_result_bytes(result)

    decompressed = zlib.decompress(output)
    assert len(decompressed) == result.raw_pixel_bytes


def test_payload_excludes_the_large_compressed_blob(crop_bytes):
    result = workload.run(crop_bytes)
    payload = result.payload()

    assert "compressed_bytes" not in payload
    assert payload["compressed_bytes_size"] == len(result.compressed_bytes)
    assert payload["compression_ratio"] > 1.0
