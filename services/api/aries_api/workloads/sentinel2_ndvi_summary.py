import json
from dataclasses import dataclass

import numpy as np
import rasterio

WORKLOAD_SLUG = "sentinel2-ndvi-summary"
DETECTOR_VERSION = "ndvi-summary-v1"
VEGETATION_NDVI_THRESHOLD = 0.3
_PERCENTILE_POINTS = (5, 25, 50, 75, 95)


@dataclass(frozen=True)
class NDVISummaryResult:
    detector_version: str
    width: int
    height: int
    band_count: int
    valid_pixel_fraction: float
    ndvi_mean: float
    ndvi_min: float
    ndvi_max: float
    ndvi_std: float
    ndvi_percentiles: dict[str, float]
    vegetation_fraction: float
    input_bytes: int

    def payload(self) -> dict:
        return {
            "workload": WORKLOAD_SLUG,
            "detector_version": self.detector_version,
            "raster": {
                "width": self.width,
                "height": self.height,
                "band_count": self.band_count,
            },
            "valid_pixel_fraction": self.valid_pixel_fraction,
            "ndvi": {
                "mean": self.ndvi_mean,
                "min": self.ndvi_min,
                "max": self.ndvi_max,
                "std": self.ndvi_std,
                "percentiles": self.ndvi_percentiles,
            },
            "vegetation_fraction": self.vegetation_fraction,
            "input_bytes": self.input_bytes,
            "limitations": (
                "Deterministic NDVI summary statistics computed from a real Sentinel-2 "
                "L2A B04 (red) / B08 (NIR) crop; not a validated land-cover classification "
                "product."
            ),
        }


def run(payload: bytes) -> NDVISummaryResult:
    """Compute an NDVI summary from a 2-band (red, NIR) GeoTIFF crop.

    NDVI = (NIR - red) / (NIR + red), computed only over pixels where both
    bands are non-zero (Sentinel-2 L2A uses 0 as nodata). Deterministic and
    model-free by design: no ONNX/ML dependency for the first real workload,
    so results are independently verifiable from the raw pixel values alone.
    """
    with rasterio.io.MemoryFile(payload) as memfile:
        with memfile.open() as src:
            if src.count < 2:
                raise ValueError("Sentinel-2 crop must contain at least 2 bands (red, NIR)")
            red = src.read(1).astype(np.float32)
            nir = src.read(2).astype(np.float32)
            width, height = src.width, src.height

    valid = (red > 0) & (nir > 0)
    valid_fraction = float(valid.mean()) if valid.size else 0.0

    denom = red + nir
    ndvi = np.zeros_like(red, dtype=np.float32)
    safe = valid & (denom > 0)
    ndvi[safe] = (nir[safe] - red[safe]) / denom[safe]

    values = ndvi[valid] if valid.any() else np.zeros(1, dtype=np.float32)
    percentiles = {
        str(point): round(float(np.percentile(values, point)), 6)
        for point in _PERCENTILE_POINTS
    }

    return NDVISummaryResult(
        detector_version=DETECTOR_VERSION,
        width=width,
        height=height,
        band_count=2,
        valid_pixel_fraction=round(valid_fraction, 6),
        ndvi_mean=round(float(values.mean()), 6),
        ndvi_min=round(float(values.min()), 6),
        ndvi_max=round(float(values.max()), 6),
        ndvi_std=round(float(values.std()), 6),
        ndvi_percentiles=percentiles,
        vegetation_fraction=round(float((values > VEGETATION_NDVI_THRESHOLD).mean()), 6),
        input_bytes=len(payload),
    )


def canonical_result_bytes(result: NDVISummaryResult) -> bytes:
    return json.dumps(
        result.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
