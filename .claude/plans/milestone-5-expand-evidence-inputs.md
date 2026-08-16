# Milestone 5: Expand Evidence Inputs (Roadmap Stage 4)
**Created**: 2026-08-16 | **Revised**: 2026-08-16 (post Vikram REFINE) | **Target**: 2026-08-20 | **Project**: Aries Stage 0

## Objective
Prove the benchmark kernel generalizes beyond one lucky workload: add `ship-detect` and `cloud-mask` (bringing the total to four real workload types alongside `satnogs-payload-anomaly-proxy` and `sentinel2-ndvi-summary`), ingest a second real Sentinel-2 scene, and add the dataset-selection plumbing that connects an AOI to the right benchmarkable object — closing the roadmap's Stage 4 exit gate: "≥2 Sentinel scenes + real SatNOGS data feed all four workload types." Watch-folder ingestion (the roadmap's other Stage 4 item) is split out to a follow-on milestone — see Revision Note below.

## Revision Note (2026-08-16, post Vikram REFINE)
Vikram's plan review found two real gaps, both fixed here before coding starts:
1. **AC4 was structurally broken**: it proposed extending `WorkloadSpec.eligible_sources` (a `frozenset[str]` keyed on data *source*, e.g. `"sentinel2"`) to distinguish which *scene* a workload runs against — but both the agricultural and coastal scenes share the same source, so that field can't do it. Fixed by giving the `Dataset.aoi_id` column (already present, currently just a placeholder `1`) real meaning: a small static AOI registry (`AOI_GHRCE_AGRICULTURAL = 1`, `AOI_COASTAL_PORT = 2`, documented in code, not a new table/migration) plus a new `WorkloadSpec.eligible_aoi_ids: frozenset[int] | None` field (`None` = any AOI for that source). `ship-detect` sets `eligible_aoi_ids={AOI_COASTAL_PORT}`; `ndvi-summary`/`cloud-mask` set `eligible_aoi_ids={AOI_GHRCE_AGRICULTURAL}`. No migration needed — the column already exists.
2. **Sizing**: the original plan bundled four separable efforts (2 workloads, 2nd ingestion scene, dataset-selection mechanism, watch-folder ingestion). Watch-folder ingestion is removed from this milestone's scope entirely and deferred to a follow-on milestone, since it's independently scoped work (a new polling subsystem) that doesn't depend on or block the workload/scene expansion.

## Acceptance Criteria
1. Two new workload modules exist in `services/api/aries_api/workloads/`: `ship_detect.py` and `cloud_mask.py`, registered in `benchmarks.py`'s `WORKLOAD_REGISTRY` alongside the existing two. Both are deterministic and model-free (same discipline as `sentinel2-ndvi-summary` — no ONNX/ML dependency introduced this milestone; see Scope Decision below), documented with an explicit `limitations` string in their result payload, and covered by unit tests proving deterministic output on a committed real-data fixture.
   - `cloud-mask`: per-pixel cloud/clear classification from Sentinel-2 visible + SWIR bands using a fixed brightness/reflectance threshold (not the SCL band shortcut — compute it from raw bands to prove the mechanism), output is a compact summary (cloud fraction, clear fraction, per-tile-quadrant breakdown) not a full-resolution mask image.
   - `ship-detect`: bright-pixel-cluster count against water background in a coastal/port AOI (Sentinel-2 true-color or NIR band), output is a count + bounding-region summary, not a full detection image.
2. A second real Sentinel-2 dataset is ingested: a coastal/port scene (for `ship-detect`) distinct from the existing agricultural GHRCE-region scene. Both scenes are real AWS Open Data fetches (or fixture-backed offline, mirroring the existing `SENTINEL2_FIXTURE_PATH` pattern) with checksum provenance identical to the existing Sentinel-2 ingestion path — this milestone generalizes `sentinel2_ingest.py` to accept a scene/AOI parameter rather than hardcoding one scene's config values.
3. `ndvi-summary` and `cloud-mask` run against the agricultural scene; `ship-detect` runs against the coastal/port scene. `satnogs-payload-anomaly-proxy` continues to run against real SatNOGS data (already proven in M4). All four workload×dataset combinations produce a completed `BenchmarkPair` with honest `estimated`/`simulated` power labels — this is the literal Stage 4 exit gate.
4. Dataset-selection rules: `WorkloadSpec` gains `eligible_aoi_ids: frozenset[int] | None` (see Revision Note) alongside the existing `eligible_sources`. `run_benchmark_pair`'s eligibility check extends to also verify `dataset.aoi_id in spec.eligible_aoi_ids` whenever that field is not `None`, raising the same `DatasetIneligibleError` as today's source check. **Fails closed**: if `spec.eligible_aoi_ids` is not `None` but `dataset.aoi_id` is `None` (or simply not in the set), that's `DatasetIneligibleError` — never treated as a pass. This is additive to the existing check, not a replacement — `satnogs-payload-anomaly-proxy` and `sentinel2-ndvi-summary`'s existing eligibility behavior is unchanged (verified by the existing M4 tests continuing to pass unmodified).
5. All new workloads and the second scene's ingestion are covered by offline tests (deterministic fixtures, no live network dependency in the default test run) plus a live-network smoke (mirroring the existing `SENTINEL2_FIXTURE_PATH` offline-by-default pattern). `scripts/compose_smoke.py` is extended to exercise all four workload×dataset combinations, matching the M4 precedent.
6. `EVIDENCE.md` gets one real entry per new workload×scene combination with the same rigor as the existing Sentinel-2 NDVI entry (dataset provenance, checksums, DRF, recommendation, honest labels, limitations).

## Scope Decision: still no ONNX
The roadmap's Stage 3 description mentions "the same ONNX model can run on Mac arm64, future Jetson arm64, and a terrestrial node," but Milestone 4 explicitly deferred ONNX Runtime as out of scope, and the project's working discipline so far has been "prove the mechanism deterministically before adding model complexity." This milestone continues that: `ship-detect` and `cloud-mask` are threshold/statistics-based, not trained models. If Abheejit wants ONNX pulled forward the way Sentinel-2 was pulled forward for the TRL 5 gate, that needs the same kind of explicit instruction and Scope Amendment — flagging here rather than deciding unilaterally.

## Approach
- Reuse the exact architecture from M4: `WorkloadSpec` registry entries, `Dataset(source="sentinel2", ...)` rows, `benchmarks.py`'s atomic pair execution — no rework, only extension. This is the same discipline Rajan's M4 audit praised ("adding the Sentinel-2 workload touched zero core logic, only added a registry entry").
- Generalize `sentinel2_ingest.py`'s hardcoded single-scene config (`SENTINEL2_ITEM_ID`, `SENTINEL2_RED_HREF`, etc.) into a small per-scene config structure so a second scene doesn't require duplicating the whole module — but keep it a static, explicit list of known scenes (not a dynamic STAC-search-at-runtime feature; that's a bigger, separate capability).
## Files Affected
- New: `services/api/aries_api/workloads/ship_detect.py`, `cloud_mask.py`
- `services/api/aries_api/sentinel2_ingest.py` (generalize to multi-scene, add AOI registry), `benchmarks.py` (registry entries + `eligible_aoi_ids` eligibility check), `config.py` (second scene's config), `models.py` (no schema change — `aoi_id` column already exists)
- `scripts/compose_smoke.py`, `EVIDENCE.md`
- New tests: `test_ship_detect_workload.py`, `test_cloud_mask_workload.py`, extensions to `test_benchmarks.py` and `test_sentinel2_ingest.py`
- New fixtures: one coastal/port Sentinel-2 crop (real data, small, mirroring the existing 128×128 fixture pattern)

## Tests Required
- Unit tests for each new workload: deterministic output on a committed real-data fixture, correct handling of edge cases (e.g., zero-cloud scene, zero-ship scene) without crashing or producing nonsense results.
- Ingestion tests: multi-scene dedup/checksum behavior unchanged from the single-scene case; each scene's `aoi_id` is correctly assigned and distinct.
- `test_benchmarks.py` extended: all four workload×dataset eligibility combinations pass; cross-combinations (e.g., `ship-detect` against the agricultural scene) correctly raise `DatasetIneligibleError` via the new AOI check. Existing M4 tests for the first two workloads pass unmodified (proves this is additive, not a rework).
- `compose_smoke.py`: all four workload×dataset pairs verified end-to-end, fixture-backed by default.

## Out of Scope
- ONNX Runtime, trained/pretrained models (see Scope Decision above)
- Dynamic STAC search / arbitrary scene selection at request time
- Watch-folder ingestion for "eventual GHRCE output" (deferred to a follow-on milestone per the Revision Note — independently scoped, doesn't block this milestone)
- React/Vite dashboard rework (Stage 5)
- Redis/RQ async execution (Stage 3, still not started)
- Report/PDF generation (Stage 6)

## Dependencies
- Completed Milestone 4 (workload registry, benchmark kernel, Sentinel-2 ingestion pattern)
- Docker Desktop with Compose v2
- AWS Open Data access for the second live scene (no-sign-request, as already proven)

## Design Considerations
No dashboard changes required beyond what M4 already built (the dashboard already shows "latest pair across all workloads" and labels which workload produced the numbers) — but worth a quick check that four workload types rotating through that single slot doesn't read as confusing without a matrix view (that's explicitly Stage 5's job, not this milestone's).

## Operational Considerations
- New live-network dependency (second Sentinel-2 scene fetch) gets the same timeout/logging discipline M4's audit required for the first one (`GDAL_HTTP_TIMEOUT`, failure logging) — no repeat of that finding.

## Fundability / Demo Value
This is what turns "one lucky workload proves the concept" into "the benchmark kernel is a real, general mechanism" — four different real workloads, two real scenes, one real telemetry source, all through the same atomic pipeline. That breadth is what the grant's "Expected Outcomes / Deliverables" and "Commercialization / Scaling Potential" fields need to point to.
