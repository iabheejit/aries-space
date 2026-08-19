"""Standalone landcover-classifier timing run for a physically separate
low-power ARM device (target: Raspberry Pi 4B, 2GB RAM).

Why this script exists: the existing "edge" measurement for this workload
(see services/api/aries_api/workloads/sentinel2_landcover_classifier.py)
is a real ONNX inference run, but it executes on the same Apple Silicon
host as the "ground" run, single-thread-constrained as a stand-in for
edge-class silicon. That is disclosed honestly in EVIDENCE.md, but a
genuinely separate physical device is stronger evidence than a thread
limit on the dev laptop. This script runs the identical model against the
identical fixture crop on real, distinct hardware and reports raw timing
-- no artificial thread constraint, because the Pi's own 4x Cortex-A72 @
1.5GHz / 2GB RAM is already edge-class; constraining it further would
misrepresent the device.

Usage (on the Pi, after copying this repo + a Python env with numpy,
onnxruntime, and rasterio installed -- see docstring at the bottom for the
one-time setup commands):

    python3 scripts/pi_landcover_benchmark.py \\
        --model services/api/aries_api/ml_models/landcover_mlp.onnx \\
        --fixture services/api/aries_api/fixtures/sentinel2_crop_43QHD_128.tif \\
        --iterations 15 \\
        --out pi_landcover_result.json

Copy the resulting JSON back to the dev machine and pass it to
scripts/ingest_pi_benchmark_result.py to compute real cost metrics using
Aries's existing (unmodified) cost formulas -- this script deliberately
does NOT do any cost math itself, to avoid two copies of that logic
drifting apart.
"""

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import rasterio

CLASS_NAMES = ["vegetation", "bare_soil", "cloud"]


def _read_features(payload: bytes) -> tuple[np.ndarray, int, int]:
    with rasterio.io.MemoryFile(payload) as memfile:
        with memfile.open() as src:
            if src.count < 2:
                raise ValueError("Crop must contain at least 2 bands (red, NIR)")
            red = src.read(1).astype(np.float32)
            nir = src.read(2).astype(np.float32)
            width, height = src.width, src.height

    ndvi = np.divide(nir - red, nir + red, out=np.zeros_like(red), where=(nir + red) != 0)
    brightness = (red + nir) / 2.0
    features = np.stack(
        [red / 10000.0, nir / 10000.0, ndvi, brightness / 10000.0], axis=-1
    ).astype(np.float32).reshape(-1, 4)
    return features, width, height


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    model_bytes = args.model.read_bytes()
    payload = args.fixture.read_bytes()
    features, width, height = _read_features(payload)

    session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])

    # Warm up once (session/graph init cost shouldn't pollute the timing loop).
    (probs,) = session.run(["probs"], {"features": features})

    wall_times_ms = []
    for _ in range(args.iterations):
        start = time.perf_counter()
        (probs,) = session.run(["probs"], {"features": features})
        wall_times_ms.append((time.perf_counter() - start) * 1000)

    predicted = np.argmax(probs, axis=1)
    total = predicted.size
    class_pixel_fraction = {
        name: round(float((predicted == idx).sum()) / total, 6)
        for idx, name in enumerate(CLASS_NAMES)
    }

    result = {
        "workload": "sentinel2-landcover-classifier",
        "target_label": "Raspberry Pi 4B (2GB RAM), real physically separate device",
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "python_version": platform.python_version(),
        },
        "model_path": str(args.model),
        "fixture_path": str(args.fixture),
        "raster": {"width": width, "height": height, "band_count": 2},
        "iterations": args.iterations,
        "wall_ms_median": statistics.median(wall_times_ms),
        "wall_ms_all": wall_times_ms,
        "input_bytes": len(payload),
        "class_pixel_fraction": class_pixel_fraction,
        "power_source": "NOT YET MEASURED -- fill in via a USB power meter on the Pi's supply if available, otherwise use the published Pi 4B typical-load figure and label it ESTIMATED, not MEASURED",
        "timing_basis": "measured_native_pi4b",
    }
    args.out.write_text(json.dumps(result, indent=2))
    print(f"Wrote {args.out} -- median wall time {result['wall_ms_median']:.3f} ms over {args.iterations} iterations")


if __name__ == "__main__":
    main()

# --- One-time setup on the Pi (Raspberry Pi OS, 64-bit recommended) ---
# 1. Copy this repo to the Pi (scp -r or git clone), or at minimum:
#    services/api/aries_api/ml_models/landcover_mlp.onnx
#    services/api/aries_api/fixtures/sentinel2_crop_43QHD_128.tif
#    scripts/pi_landcover_benchmark.py
# 2. python3 -m venv .venv && source .venv/bin/activate
# 3. pip install onnxruntime numpy rasterio
#    (onnxruntime wheels exist for aarch64 Linux; if pip fails to find one,
#    fall back to onnxruntime's official ARM64 Linux wheel or apt's
#    python3-onnxruntime package -- do not silently swap in a different
#    inference engine, that would break the apples-to-apples comparison)
# 4. Run the command in the module docstring above.
