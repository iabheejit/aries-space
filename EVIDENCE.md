# Aries Stage 0 Evidence Log

All timestamps are UTC. Estimated and simulated values are never presented as measured hardware evidence.

## 2026-08-15 — Storage Foundation

- Live SatNOGS observation: `14790343` (CANVAS, NORAD 68635)
- Canonical payload: 7,819 bytes
- SHA-256: `ee91360f5d364a257ae754c20179c1b2f8535772dc5da2b6d66dad69dadaf340`
- Provenance: PostgreSQL dataset row plus checksum-verified MinIO `raw` object
- Recovery: paired PostgreSQL/MinIO snapshot restored and reverified after deliberate object deletion
- Rollback: Milestone 2 SQLite backup `integrity_check=ok`, 25 observations

## 2026-08-15 — Benchmark Kernel Demo

- Workload: `satnogs-payload-anomaly-proxy`, detector `payload-proxy-v1`
- Limitation: payload/metadata completeness proxy, not decoded-frame telemetry anomaly detection
- Input: live SatNOGS observation `14790343`
- Targets: `ground-cpu` (`ESTIMATED` power) and `edge-sim` (`SIMULATED`, model `edge-sim-m4-v1`)
- Recorded pair: `2` in the local persistent database
- Observed demo reduction: approximately `12.33x`; exact value is stored per run
- Placement output: simulated edge at the configured assumptions; not a measured edge-hardware recommendation
- Visual checks: dashboard at `1440x1000` and `390x844`, both labels visible, no page-level horizontal overflow

## 2026-08-15 — Repeated Ground Measurement / Edge Model

- Pair: `5`; input: real SatNOGS observation `14790343`, 7,819 bytes
- Terrestrial node: Apple M4 MacBook Air, 10 CPU cores, application container
- Ground timing method: median of 1,000 warmed executions (`local-median-v1`)
- Ground latency: `0.012750 ms`; power: `25 W ESTIMATED`; energy: `0.000318750 J`
- Simulated edge latency: `0.051000 ms`, exactly `4x` the ground median (`edge-sim-m4-v1`)
- Simulated edge power: `15 W SIMULATED`; energy: `0.000765000 J`
- Both targets produced the same 381-byte analytical output; DRF `20.5223x`
- Ground cost per completed run: `₹0.000000354875`; simulated-edge cost: `₹0.000000001700`
- Power limitation: Apple Silicon exposes no RAPL measurement in this setup, and no Jetson is attached. These energy/cost values remain estimated/simulated, not measured hardware evidence.

## 2026-08-16 — Sentinel-2 NDVI Benchmark (TRL 5 Evidence)

**Why this run exists**: the DoT/TCOE application form requires TRL 5–8 ("validated prototype stage") to be eligible at all. The SatNOGS payload-proxy workload above is a JSON-metadata record whose output is larger than its input, so it structurally can never produce a positive data-reduction / downlink-savings recommendation — `break_even_downlink_inr_per_gb` and `recommendation` were always `null` for that workload. This run adds one real, large-input workload specifically to produce a genuine, non-degenerate recommendation. See the Milestone 4 plan's "Scope Amendment — 2026-08-16" for the full rationale.

- Workload: `sentinel2-ndvi-summary`, detector `ndvi-summary-v1` — deterministic, model-free NDVI statistics (mean/min/max/std/percentiles/vegetation fraction) from a real Sentinel-2 L2A red (B04) / NIR (B08) crop. Not a validated land-cover classification product.
- Input: live Sentinel-2 L2A scene `S2C_43QHD_20260619_0_L2A` (acquired 2026-06-19T05:33:00.76Z, cloud cover 1.26%), fetched directly from AWS Open Data (`sentinel-cogs.s3.us-west-2.amazonaws.com`, no-sign-request) via a windowed HTTP range read (no full-scene download) over the GHRCE/Nagpur agricultural region (bbox ~78.8–79.3°E, 20.9–21.4°N)
- Crop: 1024×1024 pixels, 2 bands, uint16, GeoTIFF, col/row offset 5000/5000 within the tile
- Ingested dataset: id `15`, object key `sentinel2/S2C_43QHD_20260619_0_L2A/5000_5000_1024_1024.tif`, size `3,346,740 bytes`, SHA-256 `0b62199d4323d59b3f458eeabd34708e45502c5da5003f770fec28e0143b21c9`
- Benchmark pair: `7`, correlation ID `2c4e4487-3966-434d-893d-605aa83de7a4`
- `ground-cpu`: wall `54.4325 ms` (median of 15 warmed executions), power `25 W ESTIMATED`, energy `1.3608 J`, cost/run `₹0.0015150`
- `edge-sim`: wall `217.73 ms` (modeled: ground median × 4× slowdown), power `15 W SIMULATED`, energy `3.2659 J`, cost/run `₹0.0000073` (edge pays no per-hour compute rent in this model, only electricity — see assumptions below)
- Both targets: output `530 bytes` (NDVI summary JSON) vs. input `3,346,740 bytes` → **DRF 6314.6×**, `downlink_saved_bytes: 3,346,210`
- **Recommendation: `simulated_edge`**. **Break-even: ₹0.00/GB** — under the stated cost model, simulated edge is already cheaper than ground before any downlink cost is added, so any positive downlink price favors it.
- Assumptions snapshot (unchanged from the SatNOGS-proxy run): ₹8/kWh electricity, ₹500/GB downlink, ₹100/hr ground compute rent (charged only to `ground-cpu`; `edge-sim` represents already-owned onboard hardware paying electricity only, not cloud rental — this assumption is what drives the ₹0 break-even and is stated plainly, not hidden)
- Verified live via the running Compose stack (`docker compose up`, rebuilt with `rasterio` + `libexpat1` added to the image) — `POST /api/ingest/sentinel2` then `POST /api/benchmarks?dataset_id=15&workload=sentinel2-ndvi-summary`, both bearer-authenticated; reproducible via `GET /api/benchmarks/latest?workload=sentinel2-ndvi-summary`
- Dashboard: "Benchmark Comparison" section now shows this pair (dashboard displays the single most-recently-completed pair across all workloads, not hardcoded to one workload)
- Limitation: single scene, single AOI, no repeated-run p95 (15 iterations, not the 1000 used for the tiny JSON workload — heavier per-call cost required a smaller, still-representative sample; see `SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS`)

## 2026-08-16 — Expand Evidence Inputs (Milestone 5 / Roadmap Stage 4)

Second real Sentinel-2 scene, two new deterministic workloads (`cloud-mask`, `ship-detect`), and AOI-scoped dataset eligibility, all live-verified against a freshly reset Compose stack (`docker compose down --volumes` then rebuilt) with both Sentinel-2 fixtures disabled (`SENTINEL2_FIXTURE_PATH=`/`SENTINEL2_COASTAL_FIXTURE_PATH=` empty → live AWS fetch). Closes the roadmap's Stage 4 exit gate: "≥2 Sentinel scenes + real SatNOGS data feed all four workload types."

**Second scene — coastal/port**: live Sentinel-2 L2A scene `S2A_43QBA_20260428_0_L2A` (acquired 2026-04-28T05:54:10.92Z, cloud cover 2.52%), NIR band (B08) only, fetched via windowed HTTP range read over Mumbai/JNPT coastal water. Crop: 1024×1024, 1 band, uint16. Ingested dataset id `3`, object key `sentinel2/S2A_43QBA_20260428_0_L2A/0_0_1024_1024.tif`, size `1,516,117 bytes`, SHA-256 `638d0922940bf3d706e22f329b34e66a4c396f0451b8775047fad01004f3e4c1`, `aoi_id=2` (distinct from the agricultural scene's `aoi_id=1`).

**`cloud-mask`** (detector `red-nir-brightness-v1`): deterministic red+NIR joint-brightness threshold computed from raw bands (not the SCL shortcut) against the same agricultural dataset (`aoi_id=1`) used for `ndvi-summary` — proves one ingested dataset can feed multiple eligible workloads. Pair `2`, correlation ID `d4b9dba3-4764-4d01-8835-eaa11acb9d57`.
- `ground-cpu`: wall `11.22 ms`, power `25 W ESTIMATED`, energy `0.2806 J`, cost/run `₹0.0003124`
- `edge-sim`: wall `44.90 ms`, power `15 W SIMULATED`, energy `0.6735 J`, cost/run `₹0.0000015`
- Output `582 bytes` vs. input `3,346,740 bytes` → **DRF 5750.4×**. Cloud fraction: **1.78%** (quadrant breakdown: NW 1.60%, NE 0.65%, SW 2.18%, SE 2.70%) — plausible against the scene's real ~1.26% STAC-reported cloud cover, computed independently from raw pixels, not read from metadata.
- **Recommendation: `simulated_edge`, break-even ₹0.00/GB** (same cost-model driver as the NDVI run: edge pays no compute rent).

**`ship-detect`** (detector `bright-pixel-cluster-v1`): deterministic bright-pixel-cluster count against a water background in the single-band coastal NIR crop. Pair `3`, correlation ID `aa381bd2-4999-458d-bed8-20ab7325f4d7`.
- `ground-cpu`: wall `5.91 ms`, power `25 W ESTIMATED`, energy `0.1476 J`, cost/run `₹0.0001644`
- `edge-sim`: wall `23.62 ms`, power `15 W SIMULATED`, energy `0.3544 J`, cost/run `₹0.0000008`
- Output `2,264 bytes` (41 candidate grid cells) vs. input `1,516,117 bytes` → **DRF 669.7×**. `11,470` bright pixels (1.09% of the crop) flagged across 41 of 64 grid cells.
- **Recommendation: `simulated_edge`, break-even ₹0.00/GB**.
- Limitation stated plainly in the workload's own result payload: this is a statistical brightness proxy for vessel presence, not a validated ship-detection model — no ground-truth vessel count was used to score it.

**AOI-scoped eligibility, verified live (not just unit-tested)**: `POST /api/benchmarks?dataset_id=2&workload=ship-detect` (agricultural dataset against the coastal-only workload) returned `422 {"detail": "Dataset AOI '1' is not eligible for workload 'ship-detect' (eligible: [2])"}` — the same fail-closed check unit tests exercise, confirmed against the real API.

**Full four-workload matrix now real**: `satnogs-payload-anomaly-proxy` (real SatNOGS, DRF 0.97×, no recommendation by design), `sentinel2-ndvi-summary` (agricultural, DRF 6314.6×), `cloud-mask` (agricultural, DRF 5750.4×), `ship-detect` (coastal, DRF 669.7×) — all with honest `ESTIMATED`/`SIMULATED` labels, all checksum-verified, all reproducible via `scripts/compose_smoke.py` (fixture-backed, offline by default).

## 2026-08-16 — Measured-Edge AI Case Study (Milestone 6)

Closes the weakest evidence gap in the grant case: every edge number up to this point (`edge-sim`) was formula-derived — a ground-baseline median multiplied by a configured slowdown factor. This milestone adds a **real trained multi-class ML model** (`sentinel2-landcover-classifier`, an ONNX MLP over vegetation/bare-soil/cloud, trained via `scripts/train_landcover_classifier.py`) and genuinely executes and times it twice: once as a multi-threaded "ground" session, once as a single-threaded (`intra_op_num_threads=1`) "edge" session on the same host CPU (Apple Silicon), a stand-in for dedicated edge/space silicon pending real hardware partner access. Both timings are `MEASURED`, not modeled — the DB's `is_simulated` flag is `False` for both targets, and `assumptions.placement_model` states this explicitly per-pair.

**Model**: 4-feature (red, NIR, NDVI, brightness) → 8-unit hidden MLP (ReLU) → 3-class softmax (vegetation/bare-soil/cloud), trained on the committed GHRCE-agricultural fixture crop (128×128, 16,384 pixels). Held-out accuracy against its own training labels: **100%** (train: 99.96%). **Disclosed limitation, stated in EVIDENCE.md by design, not buried in code comments**: training labels are weak labels derived from the same spectral-index thresholds (NDVI/brightness) used as model input features, so this accuracy figure validates that the MLP reproduces the threshold rule under a learned decision boundary — it is not independent ground-truth land-cover validation. "Water" is out of scope for this committed model: the training crop contains zero pixels below the water NIR threshold.

**Live-verified pair** (fixture-backed 128×128 real Sentinel-2 pixel crop, reproducible via `docker compose up` + `scripts/compose_smoke.py`; a full 1024×1024 live-AWS-fetch run was attempted for a larger case-study number but hit intermittent `HTTP 206`-range read failures from this sandboxed environment's network path — a known environment limitation, not a code defect; retry from an unconstrained network is the natural follow-up). Pair `4`, correlation ID `9bba8584-66b3-4cc7-b2af-9bb97d492cf3`.
- `ground-cpu` (multi-threaded ONNX session): wall **0.783 ms** (MEASURED), power `25 W ESTIMATED`, energy `0.0196 J`, cost/run `₹0.0000218`
- `edge-measured-mac` (single-threaded ONNX session): wall **0.878 ms** (MEASURED), power `8 W ESTIMATED`, energy `0.0070 J`, cost/run `₹0.0000000155`
- Both targets: identical classification output (vegetation 8.68%, bare-soil 85.36%, cloud 5.96%, dominant class `bare_soil`) — same model, same input, only timing/target differ, confirming the edge override didn't silently fall back to a different code path
- Output `661 bytes` vs. input `52,528 bytes` → **DRF 79.5×**
- **Recommendation: `edge`. Break-even: ₹0.00/GB** — edge pays no compute rent under the stated cost model, same driver as prior workloads
- **Notable, honestly-reported nuance**: at this small crop size, single-threaded "edge" execution was *slower* than multi-threaded "ground" (0.878ms vs 0.783ms) — real ONNX Runtime thread-pool spin-up overhead exceeds the benefit of parallelism for a 16,384-pixel input. A synthetic 1024×1024-pixel timing check (not part of the committed pair, exploratory only) showed the expected inversion at scale (~23ms ground vs. ~26ms edge, edge genuinely slower under the real constraint). This is exactly the kind of result a formula-derived slowdown factor cannot produce and a measured benchmark can — the real answer depends on workload size, not a fixed assumption.
- Verified live via the running Compose stack (rebuilt with `onnxruntime==1.23.1` added to the image) — `POST /api/benchmarks?dataset_id=2&workload=sentinel2-landcover-classifier`, bearer-authenticated; reproducible via `GET /api/benchmarks/latest?workload=sentinel2-landcover-classifier`
- Dashboard: Benchmark Comparison section generalized to resolve the non-ground-cpu run dynamically (was hardcoded to `edge-sim`) so this and any future measured-edge workload render correctly
- **Recommendation label renamed** from `simulated_edge` to `edge` project-wide (API, dashboard, tests) — the old name baked in an assumption (formula-derived) that is no longer universally true now that a workload can have a genuinely measured edge target; per-run `power_source`/`model_version` fields still carry the simulated-vs-measured distinction

## 2026-08-16 — TCO Fix: Edge Is No Longer Modeled as Free Compute

**The bias, named plainly**: every recommendation in this file up to this point compared `ground = compute rental + electricity` against `edge = electricity only`. Edge hardware isn't a free sunk cost, and charging it nothing but power structurally guaranteed `break_even_downlink_inr_per_gb: 0.0` (edge cheaper than ground at any positive downlink price) regardless of the workload — the break-even number was true by construction, not by finding.

**The fix**: `calculate_run_metrics` (`metrics.py`) is unchanged; the fix is in what's charged to `compute_inr_per_hour` for edge targets (`benchmarks.py`). Every edge target (simulated or measured) now carries an amortized hardware cost: `config.EDGE_HARDWARE_CAPEX_INR` (default ₹300,000 — a space/edge-qualified AI accelerator card, a disclosed, editable estimate, not a quote) divided by `config.EDGE_HARDWARE_LIFETIME_HOURS` (default 43,800 hours = 5 years continuous operation) → **₹6.85/hour**, charged alongside electricity exactly as ground's ₹100/hour rental rate already was. Both figures are persisted in every `BenchmarkPair.assumptions` blob (`edge_hardware_capex_inr`, `edge_hardware_lifetime_hours`, `edge_compute_inr_per_hour`), not hidden.

**Result, honestly reported**: under default assumptions, the recommendation did **not** flip — all four workloads (`sentinel2-ndvi-summary`, `cloud-mask`, `ship-detect`, `sentinel2-landcover-classifier`) still recommend `edge` at ₹0.00/GB break-even. This is because ground's cloud-rental rate (₹100/hour) is still far higher per-hour than edge's amortized-CAPEX rate (₹6.85/hour), and these are all sub-5-millisecond workloads, so the CAPEX charge per run is genuinely tiny. **The honest change is not the outcome, it's the mechanism**: the ₹0.00 break-even is no longer *structurally guaranteed by construction* — it's now the output of a disclosed, adjustable assumption a reviewer can push back on. Sensitivity check (computed, not yet a UI feature): for the landcover-classifier pair, the recommendation flips to `ground` if the edge hardware's amortized rate exceeds **₹98.04/hour** — e.g., the same ₹300,000 CAPEX amortized over roughly 3,060 hours instead of 43,800 (a ~17× shorter assumed operating life), or a ~14× higher CAPEX at the same lifetime. That flip point is itself useful evidence: it tells a reviewer exactly how wrong the CAPEX/lifetime assumption would have to be before the conclusion changes, rather than asking them to trust a single static number.
- Verified live via the running Compose stack (rebuilt, fresh volumes) — all four workloads re-benchmarked, full test suite green (97 passed, 5 skipped)
- Follow-up (not yet built): expose this sensitivity check as an interactive control on the dashboard ("where does the decision flip?") rather than a one-off computed number in this file — flagged in the roadmap discussion, not built this session

## 2026-08-16 — Placement Frontier: Two Real Near-Boundary Workloads

**The gap this closes**: all five existing data-reducing workloads clustered at DRF 28×–100× — every one of them recommends `edge` decisively, which invites the fair question "if edge always wins, why do I need Aries?" The honest answer requires workloads that actually sit *near* the ground/edge boundary, not just ones that land far from it. Two new workloads were built specifically to be near-boundary by design — not by tuning numbers, but by choosing tasks whose real output genuinely isn't a tiny extracted summary the way detection/classification workloads' outputs are.

**`sentinel2-lossless-recompress`** (detector `zlib-level9-v1`): real DEFLATE (zlib, max compression) recompression of the raw pixel bytes — no semantic analysis, no information loss. Its real downlinkable output is the compressed raster itself (verified by round-tripping through `zlib.decompress` and checking the byte count matches the original raw pixel array), not a JSON summary — this is the honest distinction from every other workload in this file.
- Real result on the committed 128×128 agricultural crop: input 52,528 B → compressed 49,991 B → **DRF 1.05×**, compression ratio 1.31× (against raw unpacked pixel bytes, before container overhead).
- Recommendation: `edge`, break-even ₹0.00/GB (edge still cheaper under default assumptions) — **but** the computed sensitivity is the real story: the edge hardware rate would need to rise to only **₹627.60/hour** to flip this workload to `ground`, against a current assumption of ₹6.85/hour. That's roughly 92× headroom — compare to the detection-workload cluster below, where the same headroom is in the tens of thousands.

**`sentinel2-quicklook-thumbnail`** (detector `block-mean-decimate-4x-zlib6-v1`): real block-mean spatial decimation (each axis ÷4, so 16× fewer pixels) followed by zlib-level-6 compression — a genuine EO-operations practice (generate a coarse preview before committing to downlink the full-resolution scene), not a semantic summary. Verified deterministic; a uniform-value test scene confirms the decimation math is a true block mean, not a stub.
- Real result: input 52,528 B → compressed 3,305 B → **DRF 15.89×**.
- Recommendation: `edge`, break-even ₹0.00/GB; sensitivity: flips to `ground` above **₹34,797.85/hour** — still edge-favoring, but genuinely different from and more sensitive than the detection cluster.

**The frontier, real numbers, ordered by data reduction**:

| Workload | DRF | Recommendation | Break-even hardware rate (₹/hr, current: ₹6.85) |
|---|---|---|---|
| SatNOGS Payload Anomaly Proxy | 0.97× | *(none — no positive reduction)* | n/a |
| Sentinel-2 Lossless Recompress | 1.05× | edge | ₹627.60 |
| Sentinel-2 Quicklook Thumbnail | 15.89× | edge | ₹34,797.85 |
| Ship Detect | 28.28× | edge | ₹23,375.75 |
| Sentinel-2 Land-cover Classifier | 60.38× | edge | ₹105,531.33 |
| Cloud Mask | 90.57× | edge | ₹55,234.33 |
| Sentinel-2 NDVI Summary | 99.86× | edge | ₹24,282.96 |

**Honest reading of this table**: the *binary* recommendation is `edge` for 6 of 7 workloads under current default assumptions — that hasn't changed, and we're not pretending otherwise. What's new and real is that the *sensitivity* varies by roughly two orders of magnitude across workloads. The lossless-recompress workload is genuinely, measurably closer to its boundary than any detection workload — that's the frontier concept validated with real numbers on two real new workloads, not yet with a workload that actually crosses to `ground` under plausible assumptions. Finding one that does is the natural next step, not fabricated by adjusting these two.
- Verified live via a freshly rebuilt Compose stack (reset volumes) — all 7 workloads benchmarked in one clean run, 109 tests passing (5 new: `test_lossless_recompress_workload.py`, `test_quicklook_thumbnail_workload.py`, plus one `benchmarks.py` integration test), `compose_smoke.py` exercises both new workloads end-to-end

## 2026-08-16 — TCO Fix Round 2 (Duty Cycle): Every Workload Flips to Ground

**The question that prompted this**: after the Placement Frontier work above, all 6 data-reducing workloads still recommended `edge` — a fair challenge was raised: does "edge wins everywhere" fail the project's founding assumption that the decision genuinely depends on the workload? Investigating that question surfaced a second, larger bias in the same direction as the first TCO fix, not yet caught.

**The bias, named plainly**: TCO fix round 1 (above) amortized edge's hardware CAPEX against *active compute-time* — `CAPEX / lifetime_hours`, charged per millisecond of actual execution. That implicitly assumes the hardware runs near-continuously for its whole operating life. Real satellite payloads are bursty and power-constrained, not continuously active — researched reference point: a cited power-constrained CubeSat design runs its imaging/AI payload just **one orbit per day** ([arXiv:2501.12030](https://arxiv.org/html/2501.12030v1), "Optimizing deep learning models for on-orbit deployment"), a stark contrast to Planet's mass-mapping constellation (~100 captures/day per satellite, inferred from published area-covered figures — [eoPortal](https://www.eoportal.org/satellite-missions/planet), [Planet](https://www.planet.com/pulse/planet-launches-satellite-constellation-to-image-the-whole-planet-daily/)). Commercial smallsat/cubesat design life is typically 3–5 years, though the historical average *actual* on-orbit lifetime across 200+ launched CubeSats is only ~2.1 years ([satsearch](https://blog.satsearch.co/2023-02-10-microsatellite-and-cubesat-platforms-on-the-global-market)).

**The fix**: edge hardware CAPEX is now amortized against **expected uses over the mission**, not active time: `capex_per_run = EDGE_HARDWARE_CAPEX_INR / (EDGE_EXPECTED_RUNS_PER_DAY × 365 × years)`. Default `EDGE_EXPECTED_RUNS_PER_DAY = 1` — deliberately the conservative, cited CubeSat-realistic reference point, not the Planet-scale outlier, chosen as the stronger stress test of the edge-wins conclusion. At the default 5-year lifetime this gives **₹164.38 amortized hardware cost per run** — compare to every workload's total processing+downlink cost being a few thousandths of a rupee. `metrics.calculate_run_metrics` gained a `fixed_cost_inr_per_run` parameter (a genuinely flat per-invocation charge, distinct from the existing time-proportional `compute_inr_per_hour`); ground's rental rate is untouched, since cloud compute genuinely is billed per active use — only edge's charge changed in kind, not just in magnitude.

**Result — the honest, non-hidden finding**: at the default 1 run/day, **every workload with a positive recommendation flipped from `edge` to `ground`.** The ₹164.38/run fixed hardware charge dominates every other cost term at these crop sizes, because the downlink savings involved are a few tens of kilobytes, not gigabytes.

| Workload | DRF | Recommendation | Break-even utilization (runs/day) |
|---|---|---|---|
| SatNOGS Payload Anomaly Proxy | 0.97× | *(none)* | n/a |
| Sentinel-2 Lossless Recompress | 1.05× | **ground** | 124,780.9 |
| Sentinel-2 Quicklook Thumbnail | 15.89× | **ground** | 6,674.8 |
| Ship Detect | 28.28× | **ground** | 14,079.6 |
| Sentinel-2 Land-cover Classifier | 60.38× | **ground** | 6,358.1 |
| Cloud Mask | 90.57× | **ground** | 6,326.0 |
| Sentinel-2 NDVI Summary | 99.86× | **ground** | 6,315.7 |

**Reading this honestly, not defensively**: this does not mean "edge processing never makes sense" — it means edge doesn't make sense *for a single low-frequency payload processing small crops*, under a conservative CubeSat-realistic duty cycle, at the CAPEX assumed. The break-even utilization column is itself the useful product: it tells an operator exactly how many times per day their hardware would need to run to justify its cost — e.g. NDVI Summary would need ~6,316 runs/day (clearly unrealistic for a single AOI monitor) vs. lossless-recompress needing ~124,781/day (even more unrealistic, since its output isn't meaningfully smaller than its input). That both spread across a real order of magnitude, driven by real measured differences in output size and processing cost, is the placement-frontier concept working as intended — just pointing the opposite direction from where it pointed before this fix.

**What this does *not* yet prove**: that Aries's core thesis is correct, only that it hasn't been falsified — and that the earlier "edge wins everywhere" result was an artifact of an overly generous utilization assumption, not a real finding. The two open, disclosed uncertainties that would change this conclusion: (1) a genuinely high-frequency, high-volume workload (large scenes, high revisit rate, real multi-tenant hardware sharing across many workloads/day) could still favor edge — this hasn't been tested; (2) `EDGE_EXPECTED_RUNS_PER_DAY=1` was deliberately chosen as the conservative end of a real researched range (1–100/day) specifically to stress-test the prior conclusion, not because it's necessarily the right number for every target customer — it's disclosed and configurable, and the break-even utilization figures above let a reviewer immediately see what a different assumption would change.
- Verified live via a freshly rebuilt Compose stack (reset volumes) — all 7 workloads re-benchmarked, 107 tests passing (existing tests were written without assuming which side wins, so none needed rewriting for direction — only one assumption-key rename)
- Sources: [Advancing Earth Observation: A Survey on AI-Powered Image Processing in Satellites (arXiv:2501.12030)](https://arxiv.org/html/2501.12030v1), [Planet — Flock Imaging Constellation (eoPortal)](https://www.eoportal.org/satellite-missions/planet), [Planet Launches Satellite Constellation to Image the Whole Planet Daily](https://www.planet.com/pulse/planet-launches-satellite-constellation-to-image-the-whole-planet-daily/), [Microsatellite and CubeSat platforms on the global market (satsearch)](https://blog.satsearch.co/2023-02-10-microsatellite-and-cubesat-platforms-on-the-global-market)

## 2026-08-16 — Predicted Crossover: Full-Resolution Scale (PREDICTED, Not Yet Measured — since confirmed live, see 2026-08-17 entry below)

**The question**: if the duty-cycle fix above flips every workload to `ground` at the current 128×128-crop scale, is there *any* realistic real-world scale at which edge would win again — or does the conservative duty-cycle assumption kill the thesis entirely? The cost model is linear enough in wall-clock time and byte count to answer this analytically before running anything.

**The analytical crossover, computed directly from the real cost formulas**: every summary-style workload's fixed edge hardware charge (₹164.38/run) is paid for by downlink savings alone once the input scene reaches **≈328.8 MB** (`capex_per_run ÷ downlink_price_per_byte`, holding output size ≈constant since it's a tiny summary regardless of scene size) — this number falls directly out of `benchmarks.py`'s real cost formulas, not a new assumption. That is not an absurd number: a full-resolution Sentinel-2 tile (10,980×10,980 px, 2 bands at 10m resolution) is physically real, publicly available data at almost exactly this scale.

**Attempted live verification, blocked by this environment, not by the model**: a direct `curl` range-request against the real Sentinel-2 COG (the same AWS Open Data source used throughout this project) measured **~0.2 MB/s** sustained throughput from this sandboxed session — at that rate, fetching a ~400 MB tile would take 30–40+ minutes, impractical mid-session. This is a disclosed environment limitation (this session's network path), not evidence about the real AWS-to-production-environment path, which was not tested here.

**Extrapolated prediction** (linear scaling of the real measured 128×128-crop rates — pixel count ×7,359, using the real 79.8% compression ratio observed on the existing 1024×1024 real crop as the sole basis for estimating full-tile compressed size; explicitly a thin, n=1 basis, disclosed as such):

| | Ground | Edge |
|---|---|---|
| Estimated input | 384.8 MB (extrapolated compression ratio) | same |
| Wall-clock (extrapolated) | 7.0 s | 28.2 s (simulated 4× slowdown) |
| Downlink cost | ₹192.40 | ₹0.0003 (tiny output only) |
| Compute/hardware cost | ₹0.20 (rental) | ₹164.38 (fixed amortized CAPEX, unchanged by scale) |
| **Total** | **₹192.59** | **₹164.38** |

**Predicted result: `edge` wins by ≈₹28/run**, even at the conservative 1-run/day duty cycle — because at full-tile scale, the downlink cost saved (₹192) finally exceeds the fixed hardware charge (₹164), which itself doesn't grow with scene size.

**What this is and isn't**: this is a calculation, not a benchmark run — explicitly labeled PREDICTED, not MEASURED, ESTIMATED, or SIMULATED (the project's existing three-tier honesty vocabulary doesn't cover "extrapolated from a smaller real measurement," so a fourth, distinct label is used deliberately rather than overloading an existing one). It should not be presented to a grant reviewer as proven. It is, however, a real, physically-grounded answer to "does the core assumption survive at any realistic scale": yes, at full-tile resolution, using nothing but the same cost formulas already audited and the same real compression ratio already measured once. **Next real step, not yet done**: run this live from a network path that isn't bandwidth-constrained (the actual target deployment environment, not this sandbox) to confirm or refute the prediction with a genuine measurement.

## 2026-08-17 — Crossover CONFIRMED Live: Real Full-Resolution Sentinel-2 Tile, Edge Wins by ₹27.82/run

**What changed since yesterday's PREDICTED entry**: raw network throughput from this sandboxed session was re-tested and found to have genuinely improved — from ~0.2 MB/s (previous attempt, impractical) to a sustained **~3.26 MB/s** (measured via direct `curl` range-request against the real S2 COG, 100MB in 32.1s). At that speed the full-tile fetch became a ~3-minute operation instead of 30-40 minutes, so the predicted crossover was run for real instead of staying a calculation.

**Real full-resolution ingest**: `POST /api/ingest/sentinel2` against the true, unclipped Sentinel-2 tile (`SENTINEL2_CROP_WIDTH=10980`, `HEIGHT=10980`, `COL_OFF=0`, `ROW_OFF=0` — verified against the source COG's actual raster dimensions via `rasterio` before fetching, not assumed). Completed in **3:00.44**. Real object size: **384,030,932 bytes** — within 0.2% of the prior extrapolation's 384.8 MB estimate, which is itself a useful confirmation that the extrapolation method (real measured compression ratio from the small crop, scaled) was sound.

**Real benchmark, `sentinel2-ndvi-summary`, pair `2`, correlation ID `da8dce86-ca37-4ae7-8fe6-96d57ba2018f`** (required raising `BENCHMARK_TIMEOUT_SECONDS` to 300s and lowering `SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS` to 5 for this one-off run — the ground-cpu median timing loop at full-tile scale needs far more per-call time than the 10s/15-iteration defaults tuned for small crops; both are now proper `compose.yml` passthroughs, previously silently un-wired, a real operational gap this run surfaced and fixed):
- `ground-cpu`: wall **6,773.5 ms** (6.77s) — MEASURED. Predicted was 7,041ms; within 4%.
- `edge-sim`: wall **27,094.1 ms** (27.1s, formula-derived at 4× the ground median, per the existing simulated-edge model) — cost ₹164.38446/run.
- Output stayed **541–815 bytes** regardless of the 384 MB input — DRF **709,853.85×**.
- **Recommendation: `edge`. Break-even downlink: ₹427.56/GB** — below the configured ₹500/GB, so edge genuinely wins. Break-even utilization: **0.86 runs/day** — below the current 1.0/day assumption, consistent with (and confirming) the win.
- **Real total-per-insight**: ground ₹192.2040, edge ₹164.3847 — **edge wins by ₹27.82/run**. The prior day's PREDICTED entry estimated ₹192.59 / ₹164.38 / ₹28.21 margin — every figure landed within 2% of the calculation made before this run, from a genuinely different (much larger, real) input.

**What this settles, stated precisely**: the core thesis — that ground-vs-edge is a genuine, workload- and scale-dependent economic question, not a foregone conclusion either direction — now has one real, live-measured confirmation at each end of the spectrum: small/infrequent payloads favor `ground` (all 6 data-reducing workloads at 128×128-crop scale, TCO-fix-round-2 section above), and a full-resolution real scene favors `edge` (this entry), both under the same conservative 1-run/day duty-cycle assumption, both from the same unmodified cost formulas. That is the placement-frontier concept, no longer just argued for — crossed, in both directions, with real measurements on both sides.
- Verified live via the running Compose stack; `compose.yml` gained proper passthroughs for `SENTINEL2_CROP_COL_OFF/ROW_OFF/WIDTH/HEIGHT`, `SENTINEL2_FETCH_TIMEOUT_SECONDS`, `BENCHMARK_TIMEOUT_SECONDS`, and `SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS` (previously all silently un-wired — set in `.env` but never reaching the container, a real gap this experiment surfaced)
- Only `sentinel2-ndvi-summary` was run at full-tile scale this session; the other five workloads' full-tile behavior is inferred by the same cost formulas but not independently re-measured — logged as a follow-up, not claimed as done

## 2026-08-17 — Full-Tile Confirmation for the Remaining Five Workloads (4 of 5 Measured, 1 Blocked by a Real Local Memory Constraint)

**Purpose**: yesterday's crossover confirmation only re-measured `sentinel2-ndvi-summary` at full 10,980×10,980 resolution; the other five workloads were flagged as inferred-not-measured. This entry closes that gap for four of them and honestly documents why the fifth could not be closed today.

**Setup**: two real full-resolution scenes ingested — the GHRCE agricultural tile (dataset `4`, `S2C_43QHD_20260619_0_L2A:0_0_10980_10980`, 384,030,932 bytes, two bands) and, newly, the full-resolution coastal/JNPT tile (dataset `5`, `S2A_43QBA_20260428_0_L2A:0_0_10980_10980`, 180,353,124 bytes, single NIR band — `ship-detect`'s AOI, never previously fetched at full scale). `compose.yml` gained matching `SENTINEL2_COASTAL_CROP_COL_OFF/ROW_OFF/WIDTH/HEIGHT` passthroughs (the agricultural-side ones were added yesterday; the coastal ones were still missing).

| Workload | Input | DRF | Ground total ₹/run | Edge total ₹/run | Recommendation | Margin | Break-even downlink ₹/GB | Break-even utilization (runs/day) |
|---|---|---|---|---|---|---|---|---|
| `cloud-mask` | 384.0 MB | 653,113.83× | ₹192.07 | ₹164.38 | **edge** | edge wins by ₹27.69 | 427.90 | 0.86 |
| `sentinel2-quicklook-thumbnail` | 384.0 MB | 16.48× | ₹192.09 | ₹176.03 | **edge** | edge wins by ₹16.06 | 455.48 | 0.91 |
| `sentinel2-lossless-recompress` | 384.0 MB | 1.05× | ₹192.41 | ₹346.61 | **ground** | ground wins by ₹154.21 | 8,377.98 | 16.15 |
| `ship-detect` | 180.4 MB (coastal, single-band) | 69,580.68× | ₹90.20 | ₹164.38 | **ground** | ground wins by ₹74.19 | 911.35 | 1.82 |
| `sentinel2-landcover-classifier` | 384.0 MB | — | — | — | **NOT MEASURED** | — | — | — |

**Confirms the frontier concept, and adds a real nuance the smaller-crop testing hadn't surfaced**: `cloud-mask` and `sentinel2-ndvi-summary` (yesterday) both land on `edge` at this input size — consistent, DRF-driven. `sentinel2-lossless-recompress` stays on `ground` at any scale (near-1× DRF was always going to fail to clear the fixed ₹164.38 edge hardware charge; break-even downlink of ₹8,378/GB confirms this isn't close). The genuinely new finding is **`ship-detect`**: despite by far the highest DRF measured this session (69,580.68×, higher even than `cloud-mask`), it recommends `ground` — because its input is only 180 MB (single-band coastal scene, not the two-band 384 MB agricultural tile), so the absolute downlink cost it saves (~₹90) never clears the flat ₹164.38 edge hardware charge in the first place. **DRF alone does not determine placement at full scale — the absolute input size matters just as much, because the edge side's dominant cost is a flat per-run hardware charge, not proportional to how much data reduction happens.** This is a real, disclosed refinement to the frontier story, not a contradiction of it.

**`sentinel2-landcover-classifier` — genuinely blocked, not silently skipped**: two independent attempts at full-tile scale both crashed the app container (connection reset mid-request, `curl` exit 52; container `RestartCount` incremented both times; `docker inspect` does not flag `OOMKilled=true`, but the crash is consistent with the local Docker Desktop VM's shared 7.65 GiB memory ceiling being exceeded — the workload's feature-engineering step allocates four float32 arrays across all 120,560,400 pixels (~2 GB) plus ONNX Runtime's own working set, sequenced across `ground` and `edge-constrained` sessions within one benchmark pair). The other four workloads in this table have much lighter memory profiles (raw pixel bytes only, or a single 16×-decimated array) and completed without incident, which narrows the cause to this workload's specific feature-array allocation pattern rather than the full-tile fetch or the stack generally. **Not fixed today** — fixing it means either reducing the feature-engineering memory footprint (process in row-chunks instead of one 120M-row array) or running it on a host with more available memory; both are real engineering follow-ups, not attempted here to avoid scope creep into an ad hoc verification pass. Logged as an open item below.

## 2026-08-17 — Edge Hardware Evidence Pivot: Raspberry Pi 4B Replaces the Jetson Nano Acquisition Plan (Groundwork Only, Not Yet Run)

**Why**: the existing "edge" measurement for `sentinel2-landcover-classifier` is real, executed ONNX inference — but on the *same* Apple Silicon host as "ground," single-thread-constrained as a disclosed stand-in for edge-class silicon (see Milestone 6). That's honest, but a genuinely separate physical device is stronger evidence than a thread limit on the dev laptop. Rather than wait on a Jetson Nano acquisition (never actually purchased, just a placeholder in earlier planning), the founder already has a real Raspberry Pi 4B (2GB RAM) — a real, physically distinct ARM SBC much closer in class to actual satellite edge compute than "the dev laptop, throttled."

**What was built today (no Pi access from this session — groundwork only, decided explicitly with the founder rather than assumed)**:
- `scripts/pi_landcover_benchmark.py` — a standalone, dependency-light script meant to run *on* the Pi itself. Loads the same committed `landcover_mlp.onnx` model and the same real fixture crop used elsewhere, runs real inference (no artificial thread constraint — the Pi's own 4×Cortex-A72/2GB is already the edge-class device under test, constraining it further would misrepresent it), and writes a JSON of real median wall-clock timing. Power draw is explicitly left `"NOT YET MEASURED"` in the output rather than silently defaulted.
- `scripts/ingest_pi_benchmark_result.py` — runs on the dev machine, turns that raw JSON into real cost figures using Aries's actual, unmodified `calculate_run_metrics()` (not a second copy of the cost formula that could drift). Requires an explicit `--avg-watts` value and prints whether it's `MEASURED` (from a real USB power meter, if the founder gets one) or `ESTIMATED` (the Raspberry Pi Foundation's published typical-load figure, ~6.4W) — never blurs the two.
- **Both scripts were dry-run end-to-end today** (on this Mac, standing in for "does the code path work" — not claimed as a Pi measurement) against the real fixture and a synthetic result, confirmed to execute correctly and produce sane numbers. This is verified tooling, not an untested sketch — but zero numbers from it are real edge-hardware evidence yet.
- **Not done**: the actual Pi setup (OS, Python env, onnxruntime for aarch64) and the actual benchmark run. Deferred to a session where the Pi is physically set up and reachable — founder's explicit call, not a scope decision made unilaterally.

**Business-note framing change that follows from this**: EVIDENCE.md and the published business summary should stop implying a Jetson Nano is the planned real-hardware target — it never was acquired, and the Pi 4B is now the actual plan. Until the Pi run happens, the landcover classifier's edge measurement stays exactly what it already honestly is: a real, measured, single-thread-constrained run on the same host as ground — not upgraded to "hardware pilot" status prematurely.

## Pending Evidence

- Run `scripts/pi_landcover_benchmark.py` on the actual Raspberry Pi 4B once set up, then `scripts/ingest_pi_benchmark_result.py` to get real cost figures — the real next step for the edge-hardware evidence gap (see 2026-08-17 entry above)
- `sentinel2-landcover-classifier` at full-tile scale — blocked by a real local memory constraint (see earlier 2026-08-17 entry above); needs either a chunked feature-engineering rewrite or a host with more available memory
- Hosted CI screenshots for fixed desktop/mobile viewports (now automated — see `tests/test_dashboard_playwright.py`, screenshots stored as `container-smoke` CI artifacts)
- Watch-folder ingestion for "eventual GHRCE output" — deferred to a follow-on milestone (Milestone 5 plan, Revision Note)
- Additional Sentinel-2 scenes/AOIs beyond the current two
- Measured Jetson power via `tegrastats`
- GHRCE exact antenna coordinates
- Benchmark Report v0 PDF
- Demo video takes and grant-submission artifact IDs
- DoT/TCOE application: entity registration status (DPIIT/Udyam), 3-years audited financials, GHRCE Letter of Consent/Intent, itemized budget — all founder-side, not technical
