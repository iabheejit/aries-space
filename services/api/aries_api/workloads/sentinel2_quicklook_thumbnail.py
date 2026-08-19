import hashlib
import zlib
from dataclasses import dataclass

import numpy as np
import rasterio

WORKLOAD_SLUG = "sentinel2-quicklook-thumbnail"
DETECTOR_VERSION = "block-mean-decimate-4x-zlib6-v1"
DECIMATION_FACTOR = 4  # each axis reduced 4x -> 16x fewer pixels
ZLIB_LEVEL = 6  # a faster, lighter setting than lossless-recompress's max --
# real quicklook generation favors speed over ratio, unlike an archival
# recompression pass.

# Placement-frontier workload, deliberately mid-range: a real operational
# EO practice -- generate a coarse-resolution "quicklook" preview via block
# averaging before deciding whether the full-resolution scene is worth
# downlinking. Unlike the detection workloads (whose output is a tiny
# summary statistic), the quicklook's output is still real, viewable pixel
# data, just at lower resolution -- so its reduction factor should land
# between the near-1x lossless-recompress workload and the ~60-100x
# detection/summary cluster, not alongside either extreme.


@dataclass(frozen=True)
class QuicklookThumbnailResult:
    detector_version: str
    source_width: int
    source_height: int
    thumbnail_width: int
    thumbnail_height: int
    band_count: int
    input_bytes: int
    thumbnail_raw_bytes: int
    compressed_bytes: bytes
    compressed_sha256: str

    def payload(self) -> dict:
        compressed_size = len(self.compressed_bytes)
        return {
            "workload": WORKLOAD_SLUG,
            "detector_version": self.detector_version,
            "source_raster": {"width": self.source_width, "height": self.source_height},
            "thumbnail_raster": {
                "width": self.thumbnail_width,
                "height": self.thumbnail_height,
                "band_count": self.band_count,
            },
            "input_bytes": self.input_bytes,
            "thumbnail_raw_bytes": self.thumbnail_raw_bytes,
            "compressed_bytes_size": compressed_size,
            "compressed_sha256": self.compressed_sha256,
            "decimation_factor": DECIMATION_FACTOR,
            "limitations": (
                "Real block-mean spatial decimation (each axis /4) followed by "
                "zlib-level-6 compression of the thumbnail pixels -- a real, "
                "viewable lower-resolution preview, not a semantic summary. "
                "Deliberately a mid-range placement-frontier workload: the "
                "output is still pixel data (lossy at the resolution level, "
                "lossless below that), not an extracted insight."
            ),
        }


def _block_mean_downsample(band: np.ndarray, factor: int) -> np.ndarray:
    height, width = band.shape
    trimmed_h = (height // factor) * factor
    trimmed_w = (width // factor) * factor
    trimmed = band[:trimmed_h, :trimmed_w].astype(np.float64)
    reshaped = trimmed.reshape(trimmed_h // factor, factor, trimmed_w // factor, factor)
    return reshaped.mean(axis=(1, 3))


def run(payload: bytes) -> QuicklookThumbnailResult:
    with rasterio.io.MemoryFile(payload) as memfile:
        with memfile.open() as src:
            bands = src.read()
            source_width, source_height, band_count = src.width, src.height, src.count

    thumbnail_bands = np.stack(
        [_block_mean_downsample(bands[i], DECIMATION_FACTOR) for i in range(band_count)]
    ).astype(np.uint16)
    thumbnail_height, thumbnail_width = thumbnail_bands.shape[1], thumbnail_bands.shape[2]

    thumbnail_raw_bytes = thumbnail_bands.tobytes()
    compressed = zlib.compress(thumbnail_raw_bytes, level=ZLIB_LEVEL)
    return QuicklookThumbnailResult(
        detector_version=DETECTOR_VERSION,
        source_width=source_width,
        source_height=source_height,
        thumbnail_width=thumbnail_width,
        thumbnail_height=thumbnail_height,
        band_count=band_count,
        input_bytes=len(payload),
        thumbnail_raw_bytes=len(thumbnail_raw_bytes),
        compressed_bytes=compressed,
        compressed_sha256=hashlib.sha256(compressed).hexdigest(),
    )


def canonical_result_bytes(result: QuicklookThumbnailResult) -> bytes:
    return result.compressed_bytes
