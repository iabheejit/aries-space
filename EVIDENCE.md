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

## Pending Evidence

- Hosted CI screenshots for fixed desktop/mobile viewports
- Sentinel-2 datasets and imagery workloads
- Measured Jetson power via `tegrastats`
- GHRCE watch-folder pass and exact antenna coordinates
- Benchmark Report v0 PDF
- Demo video takes and grant-submission artifact IDs
