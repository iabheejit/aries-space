import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import onnxruntime as ort
import rasterio

WORKLOAD_SLUG = "sentinel2-landcover-classifier"
DETECTOR_VERSION = "onnx-mlp-landcover-v1"
MODEL_PATH = Path(__file__).resolve().parent.parent / "ml_models" / "landcover_mlp.onnx"

# Must match scripts/train_landcover_classifier.py CLASS_NAMES exactly --
# "water" is out of scope for this committed model (the training crop has
# zero water pixels; see EVIDENCE.md for the disclosed limitation).
CLASS_NAMES = ["vegetation", "bare_soil", "cloud"]

_MODEL_BYTES = MODEL_PATH.read_bytes()
_GROUND_SESSION: ort.InferenceSession | None = None
_EDGE_SESSION: ort.InferenceSession | None = None


def _ground_session() -> ort.InferenceSession:
    global _GROUND_SESSION
    if _GROUND_SESSION is None:
        options = ort.SessionOptions()
        _GROUND_SESSION = ort.InferenceSession(
            _MODEL_BYTES, sess_options=options, providers=["CPUExecutionProvider"]
        )
    return _GROUND_SESSION


def _edge_constrained_session() -> ort.InferenceSession:
    """Edge-class stand-in: single-threaded intra/inter-op execution.
    Real inference, real thread constraint -- not a formula-derived
    slowdown applied to the ground timing.
    """
    global _EDGE_SESSION
    if _EDGE_SESSION is None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        _EDGE_SESSION = ort.InferenceSession(
            _MODEL_BYTES, sess_options=options, providers=["CPUExecutionProvider"]
        )
    return _EDGE_SESSION


@dataclass(frozen=True)
class LandcoverClassifierResult:
    detector_version: str
    width: int
    height: int
    class_names: tuple[str, ...]
    class_pixel_fraction: dict[str, float]
    dominant_class: str
    input_bytes: int

    def payload(self) -> dict:
        return {
            "workload": WORKLOAD_SLUG,
            "detector_version": self.detector_version,
            "raster": {"width": self.width, "height": self.height, "band_count": 2},
            "class_names": list(self.class_names),
            "class_pixel_fraction": self.class_pixel_fraction,
            "dominant_class": self.dominant_class,
            "input_bytes": self.input_bytes,
            "limitations": (
                "Real trained multi-class MLP (ONNX Runtime inference), not a "
                "hand-written threshold -- but trained against spectral-index weak "
                "labels (NDVI/brightness thresholds), not ground-truth land-cover "
                "annotation. 'Water' is out of scope for this committed model: the "
                "training crop (GHRCE agricultural AOI) contains no water pixels. "
                "The 'edge' target is a single-core-constrained execution on this "
                "host's Apple Silicon CPU -- a real, measured stand-in for "
                "dedicated edge/space silicon, not a measurement from actual "
                "space-qualified hardware."
            ),
        }


def _read_features(payload: bytes) -> tuple[np.ndarray, int, int]:
    with rasterio.io.MemoryFile(payload) as memfile:
        with memfile.open() as src:
            if src.count < 2:
                raise ValueError("Landcover classifier crop must contain at least 2 bands (red, NIR)")
            red = src.read(1).astype(np.float32)
            nir = src.read(2).astype(np.float32)
            width, height = src.width, src.height

    ndvi = np.divide(nir - red, nir + red, out=np.zeros_like(red), where=(nir + red) != 0)
    brightness = (red + nir) / 2.0
    features = np.stack(
        [red / 10000.0, nir / 10000.0, ndvi, brightness / 10000.0], axis=-1
    ).astype(np.float32).reshape(-1, 4)
    return features, width, height


def _classify(payload: bytes, session_factory: Callable[[], ort.InferenceSession]) -> LandcoverClassifierResult:
    features, width, height = _read_features(payload)
    session = session_factory()
    (probs,) = session.run(["probs"], {"features": features})
    predicted = np.argmax(probs, axis=1)

    total = predicted.size
    class_pixel_fraction = {
        name: round(float((predicted == idx).sum()) / total, 6)
        for idx, name in enumerate(CLASS_NAMES)
    }
    dominant_class = CLASS_NAMES[int(np.argmax([class_pixel_fraction[n] for n in CLASS_NAMES]))]

    return LandcoverClassifierResult(
        detector_version=DETECTOR_VERSION,
        width=width,
        height=height,
        class_names=tuple(CLASS_NAMES),
        class_pixel_fraction=class_pixel_fraction,
        dominant_class=dominant_class,
        input_bytes=len(payload),
    )


def run(payload: bytes) -> LandcoverClassifierResult:
    """Ground-class execution: default (multi-threaded) ONNX Runtime session."""
    return _classify(payload, _ground_session)


def run_edge_constrained(payload: bytes) -> LandcoverClassifierResult:
    """Edge-class stand-in execution: single-threaded ONNX Runtime session
    on the same host CPU. Real, measured inference under a real resource
    constraint -- a proxy for dedicated edge/space silicon, not a
    measurement from actual space-qualified hardware.
    """
    return _classify(payload, _edge_constrained_session)


def canonical_result_bytes(result: LandcoverClassifierResult) -> bytes:
    return json.dumps(
        result.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
