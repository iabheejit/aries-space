"""Train the 4-class land-cover MLP used by the sentinel2-landcover-classifier
workload and export it to a committed ONNX graph.

Reproducible, offline, run once (or re-run to retrain): reads the real
Sentinel-2 GHRCE-agricultural crop already committed as a test fixture,
builds a 4-feature-per-pixel training set (red, NIR, NDVI, brightness),
weak-labels four classes from the same spectral-index thresholds already
used by the cloud-mask and NDVI workloads (disclosed, not a validated
land-cover product), trains a small MLP, and hand-builds the ONNX graph
so the only new runtime dependency is `onnx`/`onnxruntime`, not a full
export toolchain.

Usage: python3 scripts/train_landcover_classifier.py
"""

from pathlib import Path

import numpy as np
import onnx
import rasterio
from onnx import TensorProto, helper, numpy_helper
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "sentinel2_crop_43QHD_128.tif"
MODEL_DIR = REPO_ROOT / "services" / "api" / "aries_api" / "ml_models"
MODEL_PATH = MODEL_DIR / "landcover_mlp.onnx"

# "water" is deliberately excluded: the committed GHRCE-agricultural crop
# contains zero pixels below the water NIR threshold, so a water class
# would train on zero real examples -- meaningless weights presented as a
# class. Honest scope for this specific committed model is the three
# classes actually observed in this scene; water classification is a
# named limitation, not a silent gap.
CLASS_NAMES = ["vegetation", "bare_soil", "cloud"]
CLOUD_REFLECTANCE_THRESHOLD = 2000.0
VEGETATION_NDVI_THRESHOLD = 0.3
HIDDEN_UNITS = 8
RANDOM_STATE = 42


def _weak_labels(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Spectral-index weak labels -- same thresholds as cloud_mask.py /
    sentinel2_ndvi_summary.py. Disclosed limitation: this is bootstrap
    supervision from our own heuristics, not ground-truth land-cover
    annotation. It teaches the MLP to reproduce (and generalize slightly
    past) known spectral rules, not to exceed their accuracy.
    """
    ndvi = np.divide(
        nir - red, nir + red, out=np.zeros_like(red), where=(nir + red) != 0
    )
    is_cloud = (red > CLOUD_REFLECTANCE_THRESHOLD) & (nir > CLOUD_REFLECTANCE_THRESHOLD)
    is_vegetation = (~is_cloud) & (ndvi > VEGETATION_NDVI_THRESHOLD)
    labels = np.full(red.shape, CLASS_NAMES.index("bare_soil"), dtype=np.int64)
    labels[is_vegetation] = CLASS_NAMES.index("vegetation")
    labels[is_cloud] = CLASS_NAMES.index("cloud")
    return labels


def _features(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    ndvi = np.divide(
        nir - red, nir + red, out=np.zeros_like(red), where=(nir + red) != 0
    )
    brightness = (red + nir) / 2.0
    return np.stack(
        [red / 10000.0, nir / 10000.0, ndvi, brightness / 10000.0], axis=-1
    ).astype(np.float32)


def _build_onnx_graph(model: MLPClassifier) -> onnx.ModelProto:
    w1, w2 = model.coefs_
    b1, b2 = model.intercepts_
    hidden = w1.shape[1]
    n_classes = w2.shape[1]

    inp = helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, 4])
    out = helper.make_tensor_value_info("probs", TensorProto.FLOAT, [None, n_classes])

    w1_init = numpy_helper.from_array(w1.astype(np.float32), name="w1")
    b1_init = numpy_helper.from_array(b1.astype(np.float32), name="b1")
    w2_init = numpy_helper.from_array(w2.astype(np.float32), name="w2")
    b2_init = numpy_helper.from_array(b2.astype(np.float32), name="b2")

    nodes = [
        helper.make_node("Gemm", ["features", "w1", "b1"], ["h1_pre"]),
        helper.make_node("Relu", ["h1_pre"], ["h1"]),
        helper.make_node("Gemm", ["h1", "w2", "b2"], ["logits"]),
        helper.make_node("Softmax", ["logits"], ["probs"], axis=1),
    ]
    graph = helper.make_graph(
        nodes,
        "landcover_mlp",
        [inp],
        [out],
        initializer=[w1_init, b1_init, w2_init, b2_init],
    )
    model_proto = helper.make_model(
        graph,
        producer_name="aries-train-landcover-classifier",
        opset_imports=[helper.make_opsetid("", 17)],
    )
    model_proto.ir_version = 8
    onnx.checker.check_model(model_proto)
    return model_proto


def main() -> None:
    with rasterio.io.MemoryFile(FIXTURE_PATH.read_bytes()) as memfile:
        with memfile.open() as src:
            red = src.read(1).astype(np.float32)
            nir = src.read(2).astype(np.float32)

    labels = _weak_labels(red, nir)
    features = _features(red, nir).reshape(-1, 4)
    labels = labels.reshape(-1)

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=RANDOM_STATE, stratify=labels
    )

    clf = MLPClassifier(
        hidden_layer_sizes=(HIDDEN_UNITS,),
        activation="relu",
        alpha=1e-2,
        solver="lbfgs",
        max_iter=2000,
        random_state=RANDOM_STATE,
    )
    clf.fit(x_train, y_train)
    train_acc = clf.score(x_train, y_train)
    test_acc = clf.score(x_test, y_test)
    print(f"train accuracy vs. weak labels: {train_acc:.4f}")
    print(f"held-out accuracy vs. weak labels: {test_acc:.4f}")
    print("class distribution (train):", np.bincount(y_train, minlength=4))

    onnx_model = _build_onnx_graph(clf)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    onnx.save(onnx_model, MODEL_PATH)
    print(f"wrote {MODEL_PATH} ({MODEL_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
