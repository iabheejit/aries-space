# Milestone 6: Measured-Edge AI Case Study (Roadmap Stage 5 pull-forward)
**Created**: 2026-08-16 | **Target**: 2026-08-17 | **Project**: Aries

## Objective
Replace the weakest evidence gap in the grant case — every edge number in EVIDENCE.md today is `SIMULATED` (formula-derived) — with a genuine trained ML model, run for real on both a ground-class and an edge-class execution profile on this machine, producing `MEASURED` timing for both sides of at least one workload. This is the concrete artifact behind the founder's ask: "actual numbers for something," not a projection.

## Why this is a new workload, not a formula swap
The four existing workloads (SatNOGS proxy, NDVI, cloud-mask, ship-detect) are hand-written deterministic band-math/heuristics — legitimate, but not "an AI workload." This milestone adds a real trained multi-class model (land-cover classification: vegetation / water / cloud / bare-soil, per-pixel, over the real Sentinel-2 GHRCE-agricultural crop already in the repo) run via ONNX Runtime — genuine matrix multiplication, not a threshold.

## Acceptance Criteria
1. A `sentinel2-landcover-classifier` workload exists with a real trained ONNX model (weights committed, produced by a documented, reproducible training script — not hand-set), registered in `WORKLOAD_REGISTRY`.
2. `WorkloadSpec` gains an optional per-workload edge override (`edge_run`, `edge_target_slug`, `edge_target_name`, `edge_power_source`, `edge_model_version`, `edge_avg_watts`, `edge_is_simulated`) so a workload can declare a genuinely-executed edge path instead of the formula-derived `edge-sim` default. Existing 4 workloads are unaffected (all fields default to today's simulated behavior) — zero regression risk.
3. For the new workload, both `ground-cpu` and the new `edge-measured-mac` target run the *same trained model* through onnxruntime, but under different real `SessionOptions` (ground: default multi-thread; edge: `intra_op_num_threads=1` as an edge-class stand-in), each with real wall-clock median timing over N samples — `is_simulated=False` on both, honestly labeled `timing: measured / power: estimated` (mirrors the existing ground-cpu convention).
4. `edge-measured-mac`'s honesty label in the API/dashboard explicitly states it is a resource-constrained execution on the host Apple Silicon CPU — a stand-in for dedicated edge/space silicon, not measurement from space-qualified hardware.
5. `EVIDENCE.md` gets a new entry with real numbers from this workload: model architecture, accuracy against held-out pixels, measured ground vs. measured-edge wall-clock, resulting recommendation/break-even.
6. Existing 64+ test suite still green; new tests cover: model inference determinism, edge-constrained path actually uses 1 thread (session options assertion), classifier output shape/class validity, WorkloadSpec edge-override defaults preserve old behavior for the 4 pre-existing workloads.
7. `compose_smoke.py` exercises the new workload end-to-end against the live stack.

## Approach
- Train offline via `scripts/train_landcover_classifier.py`: reads the existing real `tests/fixtures/sentinel2_crop_43QHD_128.tif` (or the full ingested crop) red+NIR bands, builds a 4-feature vector per pixel (red, nir, ndvi, brightness), weak-labels 4 classes from spectral-index thresholds, trains a small MLP (numpy, 2 hidden layers), exports weights into a hand-built ONNX graph (`onnx` package, `Gemm`→`Relu`→`Gemm`→`Softmax`) to `services/api/aries_api/ml_models/landcover_mlp.onnx`. Script is committed and reproducible; weak-label thresholds and accuracy against them are disclosed as a limitation (this is a real model with real inference cost, not a validated remote-sensing product).
- New deps: `onnx`, `onnxruntime` — network-installable per verification, added to `requirements.txt`, image rebuilt.
- Workload module `workloads/sentinel2_landcover_classifier.py`: `run()` (ground session, default threads) and `run_edge_constrained()` (edge session, 1 thread) both load the same `.onnx` file via a small cached-session helper.
- `benchmarks.py`: extend `WorkloadSpec` with the six new optional fields (defaults preserve current behavior byte-for-byte); generalize `_seed_catalog`'s second target row and `_execute_target`'s non-simulated branch to use spec-driven values instead of hardcoded `"edge-sim"`/`spec.run`; generalize `run_benchmark_pair`'s `by_slug["edge-sim"]` lookup to `by_slug[spec.edge_target_slug]`.
- `config.py`: add `EDGE_MEASURED_WATTS` (estimated draw for the constrained profile, disclosed as estimated).

## Files Affected
`requirements.txt`, `Dockerfile` (no change expected), `services/api/aries_api/config.py`, `services/api/aries_api/benchmarks.py`, `services/api/aries_api/workloads/sentinel2_landcover_classifier.py` (new), `services/api/aries_api/ml_models/landcover_mlp.onnx` (new, committed binary), `scripts/train_landcover_classifier.py` (new), `scripts/compose_smoke.py`, `tests/test_landcover_classifier_workload.py` (new), `tests/test_benchmarks.py`, `EVIDENCE.md`.

## Tests Required
Per acceptance criteria 6 above — see file list. `pytest` full suite must stay green; new tests must independently verify AC1–4 (fail if the edge path silently falls back to simulation, fail if thread constraint isn't applied, fail if old workloads' seeded targets change).

## Out of Scope
Real space/Jetson hardware measurement (still pending partner access, per `biz/orbital-compute-access-plan.md`). The dashboard visual redesign ("liquid" UI) — separate follow-up once this evidence exists to visualize. Training-data label quality validation beyond disclosed weak-label thresholds. RF/telecom-signal workloads (deferred per founder's own prioritization this session).

## Dependencies
Milestone 5 (AOI/workload-registry pattern) — complete. Live network access to install `onnx`/`onnxruntime` in the Docker build — verified.

## Design Considerations
Dashboard changes are additive only in this milestone (new workload shows up in the existing benchmark-comparison card, same template pattern as the other four) — no new UI surface yet.

## Operational Considerations
New Docker image layer (`onnx`, `onnxruntime` wheels) — rebuild required. Model file adds a few MB to the image; no runtime network fetch (weights are committed, not downloaded at request time), consistent with the project's no-hidden-network-calls posture.

## Revision Note — 2026-08-16, post-Vikram REFINE
Vikram returned REFINE (full review in `audit-trail.md`) with five gaps, all closed before coding:
1. **Explicit dispatch rule** — `_execute_target`'s non-simulated branch now resolves `run_fn` explicitly: `spec.run` when `target.slug == "ground-cpu"`, else `spec.edge_run` (raising `BenchmarkUnavailableError` if a non-simulated edge target has no `edge_run` — prevents the silent both-targets-run-ground-function failure mode Vikram flagged).
2. **Field count fixed at 7**: `edge_run`, `edge_target_slug`, `edge_target_name`, `edge_power_source`, `edge_model_version`, `edge_avg_watts`, `edge_is_simulated`. `ExecutionTarget.slowdown_factor` stays populated from the existing global `config.EDGE_SIM_SLOWDOWN_FACTOR` for every workload (non-nullable column) but is explicitly documented as ignored when `is_simulated=False`.
3. **Circularity caveat promoted out of code comments into EVIDENCE.md itself** (AC5 now requires it verbatim): held-out accuracy is measured against the same spectral-index thresholds used to derive the input features, so it validates that the MLP reproduces the threshold rule under noise, not independent ground-truth land-cover accuracy.
4. **`assumptions_snapshot()` now takes `spec`** and branches: simulated-edge workloads keep today's `edge_sim_watts`/`edge_sim_slowdown_factor`/placement-model text; measured-edge workloads instead persist `edge_measured_watts` (from `spec.edge_avg_watts`) and an explicit note that edge timing is genuinely measured, power remains an estimate. No workload's persisted `BenchmarkPair.assumptions` misrepresents its own methodology.
5. **Timeout sizing verified empirically** before finalizing `sample_iterations` for this workload — real single-thread ONNX inference latency measured locally first; `BENCHMARK_TIMEOUT_SECONDS` headroom confirmed, not assumed.

## Fundability / Demo Value
This is the single piece of evidence in the grant case that currently reads as strongest to a skeptical reviewer: a real trained model, executed twice with different real thread constraints on the same machine, both timings measured — not modeled. It also directly seeds the "space AI data center" and telecom-operator generalization the founder raised this session: the same `edge_run` override mechanism this milestone builds is exactly what a future "run this on a real space/edge partner node" or "run this on a telecom edge server" target would plug into.
