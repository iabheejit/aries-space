# Milestone 4: Benchmark Kernel and Money Chart
**Created**: 2026-08-15 | **Target**: 2026-08-20 | **Project**: Aries Stage 0

## Objective
Run the same real SatNOGS payload-anomaly proxy against a terrestrial CPU target and a clearly simulated edge target, persist an atomic and auditable comparison, and show an honest placement recommendation.

## Acceptance Criteria
1. Alembic migration `0002` adds `workloads`, `execution_targets`, `benchmark_pairs`, and `benchmark_runs`. A pair snapshots dataset ID/checksum, workload detector version, assumptions, required targets, and status. A run references its pair with unique `(pair_id, target_id)` and records result object key/checksum, input/output bytes, wall/inference milliseconds, average watts, energy joules, power source, simulation model version, and timestamps. `power_source` is constrained to `estimated`, `simulated`, or `measured_external`.
2. The workload ID is `satnogs-payload-anomaly-proxy`, visibly described as a payload/metadata proxy rather than decoded-frame telemetry anomaly detection. It consumes canonical JSON from a SatNOGS dataset and uses a versioned, deterministic feature set (payload byte size, optional artifact/decoded-data presence, station/frequency fields) and fixed threshold. Its canonical `result.json` contains detector version, score, flag, feature values, `input_bytes`, `output_bytes`, `wall_ms`, and `inference_ms`. Tests pin the fixture score and flag. A true `telemetry-anomaly` ONNX workload begins only when a checksum-pinned decoded-frame fixture is available.
3. `ground-cpu` and `edge-sim` are seeded targets. `ground-cpu` reports `power_source=estimated`. `edge-sim` reports `power_source=simulated` and applies a versioned deterministic model: baseline local kernel time multiplied by a configured slowdown factor, fixed simulated watts, and bounded per-target timeout. Each run persists the model version and labels simulated latency as modeled, not measured. No Mac or simulation measurement is presented as measured edge performance.
4. `POST /api/benchmarks` accepts one eligible stored dataset (`source=satnogs` with a linked observation), creates a pair, and executes both targets synchronously. It returns 201 only after two verified result objects and two completed runs commit. Object-write, target-execution, checksum, or database failure rolls back pair/run rows and deletes only objects created by that request; response is 503 with no completed pair. An unknown dataset ID returns 404; a known dataset without `source=satnogs` or a linked observation returns 422. Repeating a valid request creates a separately timestamped pair.
5. Metrics code calculates and persists: data reduction factor, downlink bytes/time saved at configurable default 100 Mbps, energy per completed workload invocation, target cost per completed run, and break-even downlink price. It models terrestrial placement as downlinking `input_bytes` then processing on ground, and edge placement as processing first then downlinking `output_bytes`. Pair assumptions snapshot ₹8/kWh, ₹500/GB downlink, and ₹100/hr ground compute. Hand-computed tests pin every formula, zero output/saved bytes, and invalid-input failures. Recommendation is `ground` at or below break-even and `simulated edge` strictly above it; no recommendation when saved bytes are zero or metrics are incomplete.
6. `GET /api/benchmarks/latest?workload=satnogs-payload-anomaly-proxy` selects the latest completed pair by pair completion timestamp/ID and returns input provenance, assumption snapshot, both target runs, metrics, and the recommendation. It returns 404 if no completed pair exists and refuses to serialize a recommendation from any incomplete pair.
7. The existing dashboard gains a **Benchmark Comparison** section after mission health. It shows dataset provenance, assumptions, target labels, latency, energy, cost per completed run, an explicit data-reduction callout, and a plain-language break-even statement. `edge-sim` visibly displays `SIMULATED`; ground power visibly displays `ESTIMATED`; incomplete/unavailable pairs render an explicit no-recommendation state.
8. `python scripts/demo.py` deterministically ingests the captured real SatNOGS fixture if needed, runs the pair, and prints the result URL. It never calls external upstreams. Live benchmark execution and broad demo polish are deferred until the atomic kernel passes.
9. Full tests pass offline. Focused API tests assert eligibility/status contracts, pair atomicity under object-write/execution/checksum/commit failures, latest-pair ordering, recommendation boundaries, and power labels. Dashboard tests cover normal, incomplete, and unavailable states plus screenshots at `1440x1000` and `390x844`, stored as CI artifacts with Playwright assertions for Benchmark Comparison, no viewport overflow, `SIMULATED`, and `ESTIMATED`. Compose smoke proves pair/result persistence across app recreation.

## Approach
- Use a synchronous service-layer executor for the first pair. Redis/RQ and independently polling runners begin only after the workload/result contract is proven; this is intentional scope control, not a substitute for the future runner protocol.
- Keep the proxy workload pure and deterministic over canonical raw payload JSON. It does not claim decoded-frame anomaly detection.
- Write `result.json` to MinIO `results` and store its checksum. Store metrics in PostgreSQL for comparison queries.
- Model `edge-sim` honestly as a calibrated constraint model: deterministic delay plus a configured simulated wattage. The M4 UI and API use “simulated edge node,” never “edge hardware” or “measured.”
- Cost defaults are explicit configuration, not market claims: ground electricity ₹8/kWh, downlink ₹500/GB, ground compute ₹100/hr, 100 Mbps downlink. The dashboard exposes the inputs used by the current recommendation.
- Preserve existing MissionOps routes and dashboard sections. This milestone adds one comparison surface; React, Redis, Sentinel-2, and ONNX model files remain deferred.

## Metrics
- `DRF = input_bytes / output_bytes`; zero output is invalid and produces no recommendation.
- `energy_joules = avg_watts * wall_ms / 1000`.
- `downlink_saved_bytes = max(input_bytes - output_bytes, 0)`.
- `downlink_saved_seconds = downlink_saved_bytes * 8 / (downlink_mbps * 1_000_000)`.
- `target_cost_inr = energy_joules / 3_600_000 * electricity_inr_per_kwh + wall_ms / 3_600_000 * compute_inr_per_hour`; this is cost per completed workload invocation, not a claim about anomaly quantity.
- `break_even_downlink_inr_per_gb = max(edge_cost_inr - ground_cost_inr, 0) / (downlink_saved_bytes / 1_000_000_000)`; no recommendation when saved bytes are zero.

## Files Affected
- `services/api/alembic/versions/0002_benchmark_kernel.py`
- `services/api/aries_api/models.py`, `config.py`, `main.py`, `storage.py`
- New `services/api/aries_api/benchmarks.py`, `metrics.py`, `workloads/satnogs_payload_proxy.py`
- `services/api/aries_api/templates/dashboard.html`
- `scripts/demo.py`, `scripts/compose_smoke.py`, `README.md`
- New focused benchmark/metrics/API/dashboard tests

## Tests Required
- Unit tests pin each metric formula with exact expected values and invalid-input boundaries.
- Workload tests prove same fixture input yields byte-identical result output, detector version, expected score/flag, and schema.
- Repository tests prove results object checksum, target labels/model version, pair atomicity, and run persistence.
- API tests prove eligibility/status codes, object/execution/checksum/commit compensation, recommendation refusal, latest ordering, and each honest power-source label.
- Dashboard tests assert Benchmark Comparison, provenance, assumptions, DRF text, break-even statement, `SIMULATED`, `ESTIMATED`, incomplete and unavailable states, at `1440x1000` and `390x844`; CI stores screenshots as job artifacts rather than brittle image baselines.
- Compose smoke verifies migration, fixture benchmark pair, MinIO result object integrity, and persistence across app recreation.

## Out of Scope
- Redis/RQ, asynchronous job dispatch, dead-runner recovery, or remote runner protocol
- ONNX Runtime and trained/pretrained model files; the payload proxy does not represent the future ONNX telemetry-anomaly workload
- Watch-folder ingestion, ship detection, cloud masking
- Ground GPU, Jetson, `tegrastats`, external power measurement, or performance claims about real orbital hardware
- React/Vite, Recharts, chart PNG export, report/PDF generation, or `/api/v1` redesign
- Automated placement/routing beyond the evidence-backed recommendation text

### Scope Amendment — 2026-08-16
The DoT/TCOE application form (`Application Form.pdf`, §5) requires **TRL 5–8** ("validated prototype stage") to be eligible at all; below TRL 5 is not considered. The SatNOGS payload-anomaly-proxy workload (AC5 above) is a tiny JSON-metadata record whose derived output is *larger* than its input, so it can never produce a positive data-reduction/downlink-savings story — `break_even_downlink_inr_per_gb` and `recommendation` are structurally always `null` for that workload alone, which reads as "no working recommendation," i.e. below the TRL 5 bar.

Per Abheejit's explicit instruction ("Finish M4's exit gate for real — a Sentinel-2-scale input producing an actual break_even_downlink_inr_per_gb number. This is now both the roadmap milestone and the TRL 5 eligibility gate, not two separate things."), Sentinel-2/NDVI was pulled forward from Milestone 4's original Out of Scope list and from the roadmap's Stage 4 ("Expand Evidence Inputs") into this milestone, narrowly: one real Sentinel-2 L2A red/NIR crop (AWS Open Data, no-sign-request), one deterministic NDVI-summary workload, added to the same generalized benchmark kernel (not a rewrite) via a small workload registry in `benchmarks.py`. Ship-detect, cloud-mask, watch-folder ingestion, and broader multi-scene evidence remain deferred to Stage 4 proper.

**Result**: `sentinel2-ndvi-summary` on a real 3,346,740-byte crop produced DRF 6314.6×, `recommendation: "simulated_edge"`, `break_even_downlink_inr_per_gb: 0.0` (edge is cheaper than ground at any positive downlink price under the stated assumptions) — a genuine, non-degenerate, formula-traceable recommendation. See `EVIDENCE.md` for full run details. This is treated as the milestone's TRL 5 evidence; the original AC5/AC6 satnogs-proxy acceptance criteria are unchanged and still hold for that workload.

## Dependencies
- Completed Milestone 3 PostgreSQL/MinIO data foundation and real captured SatNOGS fixture
- Docker Desktop with Compose v2 on the M4 development machine
- No external API access for deterministic demo validation

## Design Considerations
The dashboard must let a non-technical reviewer scan the story in order: Mission Health → Benchmark Comparison → passes and observations. Comparison labels must not imply simulation equals measured hardware. The recommendation must name its cost and downlink assumptions in plain language and render an explicit insufficiency state when the pair cannot support one.

## Operational Considerations
- The app remains one process and one scheduler owner. Synchronous benchmark execution has a bounded per-target timeout and is suitable only for this first short telemetry workload.
- Each benchmark pair logs a correlation ID, dataset ID, workload ID, target ID, power source, and result key; logs exclude raw payloads and secrets.
- The API bearer token protects benchmark execution writes.

## Fundability / Demo Value
This is the first screen that proves the Aries thesis rather than merely its plumbing: the same real satellite-data workload runs on a terrestrial node and a simulated edge node, then displays the data/energy/cost trade-off and the downlink price where the decision changes. It remains honest about simulation while creating a reusable benchmark record for the grant application.