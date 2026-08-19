import hashlib
import json
import zlib
from dataclasses import dataclass

import numpy as np
import rasterio

WORKLOAD_SLUG = "sentinel2-lossless-recompress"
DETECTOR_VERSION = "zlib-level9-v1"
ZLIB_LEVEL = 9

# Placement-frontier workload, deliberately NOT a detection/summary task: it
# repacks the same pixels losslessly (real DEFLATE compression) rather than
# extracting an insight, so its real downlinkable output is the compressed
# raster itself, not a small JSON summary. That's why canonical_result_bytes
# below returns the actual compressed bytes rather than json.dumps(payload())
# -- unlike the detection workloads, this one's "output" and its "summary of
# the output" are genuinely different sizes.


@dataclass(frozen=True)
class LosslessRecompressResult:
    detector_version: str
    width: int
    height: int
    band_count: int
    input_bytes: int
    raw_pixel_bytes: int
    compressed_bytes: bytes
    compressed_sha256: str

    def payload(self) -> dict:
        compressed_size = len(self.compressed_bytes)
        return {
            "workload": WORKLOAD_SLUG,
            "detector_version": self.detector_version,
            "raster": {
                "width": self.width,
                "height": self.height,
                "band_count": self.band_count,
            },
            "input_bytes": self.input_bytes,
            "raw_pixel_bytes": self.raw_pixel_bytes,
            "compressed_bytes_size": compressed_size,
            "compressed_sha256": self.compressed_sha256,
            "compression_ratio": (
                round(self.raw_pixel_bytes / compressed_size, 4)
                if compressed_size
                else None
            ),
            "limitations": (
                "Real DEFLATE (zlib level 9) recompression of the raw pixel bytes "
                "-- lossless, no semantic analysis. Deliberately a near-1x "
                "placement-frontier workload: unlike the detection/summary "
                "workloads, its output IS the (compressed) data, not an "
                "extracted insight, so it should NOT be expected to show a "
                "large data reduction factor."
            ),
        }


def run(payload: bytes) -> LosslessRecompressResult:
    with rasterio.io.MemoryFile(payload) as memfile:
        with memfile.open() as src:
            bands = src.read()
            width, height, band_count = src.width, src.height, src.count

    raw_pixel_bytes = bands.astype(np.uint16).tobytes()
    compressed = zlib.compress(raw_pixel_bytes, level=ZLIB_LEVEL)
    return LosslessRecompressResult(
        detector_version=DETECTOR_VERSION,
        width=width,
        height=height,
        band_count=band_count,
        input_bytes=len(payload),
        raw_pixel_bytes=len(raw_pixel_bytes),
        compressed_bytes=compressed,
        compressed_sha256=hashlib.sha256(compressed).hexdigest(),
    )


def canonical_result_bytes(result: LosslessRecompressResult) -> bytes:
    # The real downlinkable payload for this workload IS the compressed
    # raster -- not a JSON description of it. This is what determines the
    # workload's data reduction factor and downlink savings.
    return result.compressed_bytes
