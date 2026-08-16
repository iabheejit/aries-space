import json
from dataclasses import dataclass

import numpy as np
import rasterio

WORKLOAD_SLUG = "cloud-mask"
DETECTOR_VERSION = "red-nir-brightness-v1"
CLOUD_REFLECTANCE_THRESHOLD = 2000.0
QUADRANT_LABELS = ("nw", "ne", "sw", "se")


@dataclass(frozen=True)
class CloudMaskResult:
    detector_version: str
    width: int
    height: int
    cloud_fraction: float
    clear_fraction: float
    quadrant_cloud_fraction: dict[str, float]
    input_bytes: int

    def payload(self) -> dict:
        return {
            "workload": WORKLOAD_SLUG,
            "detector_version": self.detector_version,
            "raster": {"width": self.width, "height": self.height, "band_count": 2},
            "cloud_fraction": self.cloud_fraction,
            "clear_fraction": self.clear_fraction,
            "quadrant_cloud_fraction": self.quadrant_cloud_fraction,
            "input_bytes": self.input_bytes,
            "limitations": (
                "Deterministic red+NIR joint-brightness threshold, computed from raw "
                "bands (not the SCL scene-classification shortcut); clouds are bright "
                "in both visible red and NIR simultaneously, unlike vegetation (dark "
                "red, bright NIR) or bare soil/water. A coarse proxy, not a validated "
                "cloud product."
            ),
        }


def run(payload: bytes) -> CloudMaskResult:
    with rasterio.io.MemoryFile(payload) as memfile:
        with memfile.open() as src:
            if src.count < 2:
                raise ValueError("Cloud-mask crop must contain at least 2 bands (red, NIR)")
            red = src.read(1).astype(np.float32)
            nir = src.read(2).astype(np.float32)
            width, height = src.width, src.height

    cloud_mask = (red > CLOUD_REFLECTANCE_THRESHOLD) & (nir > CLOUD_REFLECTANCE_THRESHOLD)

    half_h, half_w = height // 2, width // 2
    quadrants = {
        "nw": cloud_mask[:half_h, :half_w],
        "ne": cloud_mask[:half_h, half_w:],
        "sw": cloud_mask[half_h:, :half_w],
        "se": cloud_mask[half_h:, half_w:],
    }
    quadrant_cloud_fraction = {
        label: round(float(quadrant.mean()), 6) if quadrant.size else 0.0
        for label, quadrant in quadrants.items()
    }

    cloud_fraction = round(float(cloud_mask.mean()), 6)
    return CloudMaskResult(
        detector_version=DETECTOR_VERSION,
        width=width,
        height=height,
        cloud_fraction=cloud_fraction,
        clear_fraction=round(1.0 - cloud_fraction, 6),
        quadrant_cloud_fraction=quadrant_cloud_fraction,
        input_bytes=len(payload),
    )


def canonical_result_bytes(result: CloudMaskResult) -> bytes:
    return json.dumps(
        result.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
