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

## Pending Evidence

- Hosted CI screenshots for fixed desktop/mobile viewports (now automated — see `tests/test_dashboard_playwright.py`, screenshots stored as `container-smoke` CI artifacts)
- Watch-folder ingestion for "eventual GHRCE output" — deferred to a follow-on milestone (Milestone 5 plan, Revision Note)
- Additional Sentinel-2 scenes/AOIs beyond the current two
- Measured Jetson power via `tegrastats`
- GHRCE exact antenna coordinates
- Benchmark Report v0 PDF
- Demo video takes and grant-submission artifact IDs
- DoT/TCOE application: entity registration status (DPIIT/Udyam), 3-years audited financials, GHRCE Letter of Consent/Intent, itemized budget — all founder-side, not technical
