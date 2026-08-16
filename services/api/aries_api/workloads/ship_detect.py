import json
from dataclasses import dataclass

import numpy as np
import rasterio

WORKLOAD_SLUG = "ship-detect"
DETECTOR_VERSION = "bright-pixel-cluster-v1"
GRID_CELLS_PER_SIDE = 8
BRIGHTNESS_SIGMA = 4.0
MIN_ABSOLUTE_THRESHOLD = 1200.0


@dataclass(frozen=True)
class ShipDetectResult:
    detector_version: str
    width: int
    height: int
    background_mean: float
    background_std: float
    bright_pixel_count: int
    bright_pixel_fraction: float
    candidate_cells: list[dict]
    input_bytes: int

    def payload(self) -> dict:
        return {
            "workload": WORKLOAD_SLUG,
            "detector_version": self.detector_version,
            "raster": {"width": self.width, "height": self.height, "band_count": 1},
            "background": {
                "mean": self.background_mean,
                "std": self.background_std,
            },
            "bright_pixel_count": self.bright_pixel_count,
            "bright_pixel_fraction": self.bright_pixel_fraction,
            "candidate_cells": self.candidate_cells,
            "input_bytes": self.input_bytes,
            "limitations": (
                "Deterministic bright-pixel-cluster count from a single Sentinel-2 NIR "
                "band over water; a statistical proxy for vessel presence, not a "
                "validated ship-detection model. Reports coarse grid-cell candidate "
                "regions, not per-pixel bounding boxes."
            ),
        }


def run(payload: bytes) -> ShipDetectResult:
    """Count bright-pixel clusters against a water background in a single-band
    NIR crop. Water strongly absorbs NIR (low, uniform reflectance); vessels
    and other above-water structures reflect far more, showing up as bright
    outliers. Deterministic and model-free: threshold is background
    mean + BRIGHTNESS_SIGMA * std (floored at MIN_ABSOLUTE_THRESHOLD so a
    near-uniform scene doesn't manufacture false positives from noise).
    """
    with rasterio.io.MemoryFile(payload) as memfile:
        with memfile.open() as src:
            band = src.read(1).astype(np.float32)
            width, height = src.width, src.height

    background_mean = float(band.mean())
    background_std = float(band.std())
    threshold = max(
        background_mean + BRIGHTNESS_SIGMA * background_std, MIN_ABSOLUTE_THRESHOLD
    )
    bright_mask = band > threshold

    cell_h = max(height // GRID_CELLS_PER_SIDE, 1)
    cell_w = max(width // GRID_CELLS_PER_SIDE, 1)
    candidate_cells: list[dict] = []
    for row in range(0, height, cell_h):
        for col in range(0, width, cell_w):
            cell = bright_mask[row : row + cell_h, col : col + cell_w]
            count = int(cell.sum())
            if count > 0:
                candidate_cells.append(
                    {
                        "row": row // cell_h,
                        "col": col // cell_w,
                        "bright_pixel_count": count,
                    }
                )

    return ShipDetectResult(
        detector_version=DETECTOR_VERSION,
        width=width,
        height=height,
        background_mean=round(background_mean, 3),
        background_std=round(background_std, 3),
        bright_pixel_count=int(bright_mask.sum()),
        bright_pixel_fraction=round(float(bright_mask.mean()), 6),
        candidate_cells=candidate_cells,
        input_bytes=len(payload),
    )


def canonical_result_bytes(result: ShipDetectResult) -> bytes:
    return json.dumps(
        result.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
