# Session Log
<!-- Reverse chronological. One entry per session. -->
<!-- Format: ## {date} | Milestone {N} | {title} -->
<!-- What was done, what's next, any RESUME markers -->

## 2026-08-16 | Milestone 5 | Roadmap Stage 4 exit gate closed: four real workloads, two Sentinel-2 scenes
**Done**:
- Drafted Milestone 5 plan (roadmap Stage 4: Expand Evidence Inputs); Vikram REFINE caught a real structural gap (proposed AOI-selection mechanism couldn't actually distinguish two scenes sharing one data source) plus a sizing concern; fixed both (AOI-scoped `eligible_aoi_ids` giving `Dataset.aoi_id` real meaning, no migration needed; watch-folder ingestion cut to a follow-on milestone) → READY
- Found and validated a second real Sentinel-2 scene (Mumbai/JNPT coastal water, S2A_43QBA_20260428_0_L2A, 2.52% cloud) via live STAC search + rasterio windowed reads, distinct from the existing GHRCE agricultural scene
- Built two new deterministic, model-free workloads: `cloud-mask` (red+NIR joint-brightness threshold from raw bands) and `ship-detect` (bright-pixel-cluster count against water, grid-cell candidate regions — no scipy needed)
- Generalized `sentinel2_ingest.py` from one hardcoded scene to a small static `SceneConfig` registry keyed by AOI id; extended `WorkloadSpec` with `eligible_aoi_ids`, checked additively (fails closed) in `run_benchmark_pair`
- Live-verified end-to-end against a freshly reset Compose stack (`down --volumes`, live AWS fetches, both Sentinel-2 fixtures disabled): all four workload×dataset combinations produced real, checksum-verified, honestly-labeled results; cross-AOI rejection (`ship-detect` against the agricultural dataset) confirmed live as a real 422, not just unit-tested
- Extended `compose_smoke.py` and CI to cover all four combinations plus the cross-AOI rejection
- Ran the 7-specialist completion audit: no blockers. Fixed both real findings same-session — Rajan's untested fail-closed AOI path (added a direct test) and Divya's opaque dataset-ID dashboard copy (added human-readable `AOI_NAMES`, dashboard now says "Mumbai/JNPT coastal water" instead of a raw scene ID)
- 89 tests passing, CI green (test 3.11/3.13 + container-smoke with Playwright), merged `milestone/5-expand-evidence-inputs` to `main`
- Full EVIDENCE.md entry with real live figures for both new workloads (DRF 5750.4× cloud-mask, DRF 669.7× ship-detect, both `simulated_edge` recommendation at ₹0.00/GB break-even)

**Next**:
- Stage 5 (Demo Surface / React dashboard, benchmark matrix view) — deferred by design, not urgent
- Watch-folder ingestion for "eventual GHRCE output" — deferred to a follow-on milestone
- Founder-side grant blockers unchanged and now the actual critical path: entity registration (DPIIT/Udyam), 3-years audited financials, GHRCE signed Letter of Consent/Intent, itemized budget, confirm document format TCOE wants

**Decisions**: Kept `ship-detect`/`cloud-mask` deterministic and model-free (no ONNX), consistent with the project's established discipline of proving the mechanism before adding model complexity — flagged explicitly in the plan as a scope decision rather than assumed silently.

**Resume**: <!-- RESUME: Milestone 5 is COMPLETED and merged to main. Roadmap Stage 4 exit gate is closed. Next session: propose Milestone 6 scope (Stage 5 Demo Surface, or pivot to grant-paperwork support) with Abheejit. -->

## 2026-08-16 | Milestone 4 | TRL 5 gate reached; git remote + M2 resolution; project identity unified
**Done**:
- Read the actual DoT/TCOE application form + program booklet (supplied by Abheejit) — found the hard gate: TRL 5-8 required to be eligible at all; project was TRL 4 ("pre-benchmark") at the time
- Resolved Milestone 2 as SUPERSEDED by Milestone 3 (its architecture was replaced before its sole blocker, no git remote, was cleared)
- Set up git remote (private `iabheejit/aries-space`), pushed all branches, merged milestones 1+3 to `main`; first remote CI run caught and fixed a real false-positive in the container-smoke "one uvicorn process" check
- Fixed stale project identity in `CLAUDE.md` (still said "MissionOps Lite"/SQLite-era stack; README/architecture docs had already moved to "Aries Stage 0")
- Built the TRL 5 evidence: added `sentinel2-ndvi-summary`, a second, real-data-reduction benchmark workload (deterministic NDVI summary from a real Sentinel-2 L2A red/NIR crop fetched live from AWS Open Data, no-sign-request) — the existing `satnogs-payload-anomaly-proxy` workload can structurally never produce a positive recommendation since its JSON output is bigger than its input
- Generalized `benchmarks.py` from one hardcoded workload to a small `WorkloadSpec`/`WORKLOAD_REGISTRY` registry
- Added `POST /api/ingest/sentinel2`, `workload=` param on `POST /api/benchmarks`; dashboard now shows the latest completed pair across all workloads (was hardcoded to the satnogs slug, silently showing a stale "no recommendation" result)
- Fixed Docker image (missing `libexpat1` for rasterio/GDAL) and pinned `rasterio==1.4.4` (1.5.1 needs Python >=3.12, breaking the 3.11 CI job)
- Live-verified end-to-end against the running Compose stack: real 3.3MB Sentinel-2 crop ingested, benchmarked, DRF 6314.6x, `recommendation: "simulated_edge"`, `break_even_downlink_inr_per_gb: 0.0` — genuine, non-degenerate, formula-traceable. Data survived a container recreate.
- Documented the scope change as an explicit "Scope Amendment" in the milestone-4 plan (Sentinel-2 was originally out of scope for M4) rather than silent drift; updated `EVIDENCE.md`
- 72 tests passing (up from 64), all offline/deterministic via a small committed real-data fixture; CI green on `milestone/4-benchmark-kernel` (not yet merged to main)
- Saved memory: DoT/TCOE grant requirements + TRL timeline, for future-session accuracy

**Next**:
- Full Milestone 4 completion audit (7 specialists) before merging to `main` — dashboard/report polish, broader Sentinel-2 evidence, and the rest of the M4 plan's acceptance criteria are still open
- Founder-side grant blockers remain: entity registration (DPIIT/Udyam), 3-years audited financials, GHRCE signed LoI, itemized budget, confirm document format TCOE wants

**Decisions**: Pulled Sentinel-2/NDVI forward from M4's original Out of Scope list and from the roadmap's Stage 4, narrowly (one workload, one scene), specifically because it's the same thing as the TRL 5 grant gate — not treated as two separate asks.

**Resume**: <!-- RESUME: milestone/4-benchmark-kernel has the TRL5 evidence, CI green, not merged to main. Next session: either continue M4 (dashboard/report polish per the original plan) or run the M4 completion audit if Abheejit considers the TRL5 evidence sufficient to move on. -->

## 2026-08-15 | Milestone 3 | Aries storage foundation implemented and audit fixes validated
**Done**:
- Cut MissionOps to one FastAPI runtime under `services/api/aries_api`, PostgreSQL 15 with Alembic, and MinIO raw-object provenance; removed the SQLite runtime package
- Preserved dashboard, pass prediction, observation/status APIs, scheduler ownership, outage behavior, and explicit approximate GHRCE campus coordinates
- Added deterministic SatNOGS object keys, canonical payload checksums, PostgreSQL advisory-lock serialization, byte-level object verification, bounded payloads, and compensating cleanup
- Added bearer authentication for ingestion writes, required Compose secrets, digest-pinned runtime images, non-root/read-only app packaging, bounded readiness, and degraded dashboard storage state
- Replaced stale SQLite CI checks with mandatory migration, PostgreSQL/MinIO concurrency, checksum, idempotency, and Compose smoke gates
- Added quiesced PostgreSQL plus MinIO manifest backup/restore; restored a deliberately deleted raw object and reverified both dataset objects
- Full local CI-equivalent suite passed: 44 tests including isolated Alembic round-trip and real concurrent PostgreSQL/MinIO ingestion
- Deterministic Compose smoke passed repeatedly on persistent data; fixture `14790266`, 368 bytes, SHA-256 `94591a7ab126058ce1c0a0a81c6b7aff35f223ec5f429ccd92a25ee13f17f98f`
- Authenticated live SatNOGS smoke passed idempotently for observation `14790343`, 7,819 bytes, SHA-256 `ee91360f5d364a257ae754c20179c1b2f8535772dc5da2b6d66dad69dadaf340`
- Milestone 2 rollback proof passed: SQLite backup `integrity_check=ok`, 25 observations; old app returned those 25 rows; Aries restarted with PostgreSQL/MinIO data intact

**Audit**:
- Final focused verdicts: Priya `PASS`, Kavitha no blockers, Rajan `SOUND`, Arjun `CLEAN`, Sanjay `SHIP_READY`; CTO call `PROCEED`
- Final rebuilt gate passed 49 tests plus compile, migration, integration, deterministic smoke, live ingestion, recovery, and rollback evidence

**Remaining external items**:
- Remote GitHub Actions execution remains unavailable because no Git remote is configured; local CI-equivalent gates pass
- Exact GHRCE antenna coordinates remain operator-supplied before pilot deployment

**Resume**: <!-- RESUME: Milestone 3 is COMPLETED at v2.0.0. Aries stack is healthy in deterministic fixture mode on 127.0.0.1:8000. Next milestone should expand ingestion or begin ONNX workload execution; do not reopen storage foundation scope. -->

## 2026-08-15 | Milestone 2 | Production hardening and local validation complete; remote CI pending
**Done**:
- Vikram reviewed the production-readiness plan twice (`REFINE`) and returned `READY` after acceptance checks were made deterministic
- Added configuration validation, SQLite WAL/foreign-key/busy-timeout durability, independent health endpoints, scheduler overlap/failure/lifecycle controls, and malformed-upstream handling
- Added non-root/read-only Docker packaging, localhost-only Compose deployment, persistent volume, `.env.example`, dependency split, operator README, backup/restore procedure, and Python 3.11/3.13 CI with mandatory container runtime checks
- Expanded the offline suite from 14 to 38 tests; `pytest`, `compileall`, Pylance workspace diagnostics, and Compose config pass (dependency deprecation warnings remain non-failing); `git diff --check` reports only two inherited EOF blank lines in the already-uncommitted Milestone 1 docs
- Canonical live smoke passed at `2026-08-15T01:08:27.164052+00:00`: Celestrak + SatNOGS, CANVAS 68635, approximate GHRCE coordinates, liveness/readiness 200, 25 observations, fresh TLE, one pass, dashboard 200
- SQLite evidence: SatNOGS observation `14780576`, 15,834-byte raw JSON, timestamp `2026-08-14 16:35:09`, station `2416`, frequency `437250000`, signal quality `good`; isolated DB removed after shutdown
- Seven-agent interim audit found no exploit blocker but rejected completion without container/CI proof; audit-driven runtime, test-fidelity, recovery, and accessibility findings were fixed
- Docker proof completed after privileged access was approved: image built, UID 10001, exactly one Python/Uvicorn process, localhost binding, readiness healthy, SQLite marker `42` persisted across recreation, and backup/restore returned marker `42` with `integrity_check=ok`
- Full 38-test suite passed in clean Python 3.11 and local Python 3.13 environments
- Production Compose service started on `127.0.0.1:8000`; it ingested 25 live observations, fetched a fresh Celestrak TLE, returned a pass, rendered the dashboard, and emitted expected scheduler/access logs
- Real-data provenance independently confirmed: stored observation `14790266` exactly matched the live SatNOGS API for CANVAS 68635, station 2545, start `2026-08-15T01:41:38Z`, including real waterfall/audio URLs
- Dashboard redesigned and verified at 1440x1000 and 390x844 with 10 live observation rows and no page-level overflow
- Session closed with the healthy Compose service intentionally stopped; persistent data remains in the `missionops-data` Docker volume

**Blocked**:
- No Git remote is configured, so the mandatory GitHub Actions workflow cannot run remotely
- Exact GHRCE antenna coordinates remain an external pilot dependency

**Next**:
- Configure a Git remote, run/push CI, and complete the Milestone 2 audit
- Confirm GHRCE antenna coordinates before pilot use

**Resume**: <!-- RESUME: Milestone 2 implementation, live validation, dashboard redesign, local Docker runtime/persistence/restore proof, and Python 3.11/3.13 checks are complete. Compose is intentionally stopped; restart with `docker compose up --detach --wait --wait-timeout 60`. Status remains BLOCKED solely on mandatory remote CI execution; no Git remote is configured. -->

## 2026-08-15 | Milestone 1 | MissionOps Lite MVP built and shipped, COMPLETED
**Done**:
- First session: bootstrapped Mr Fox infrastructure (agents, commands, state files) in the empty aries-space repo
- Drafted Milestone 1 plan, Vikram REFINE → fixed 4 gaps (quantified AC1/AC3/AC5, added Security Considerations, outage handling) → Vikram READY
- Confirmed satellite choice against live SatNOGS data: CANVAS (NORAD 68635) — alive, actively observed, has a registered decoder
- Confirmed GHRCE has no registered SatNOGS station (checked all ~4,400); used public approximate coordinates as documented placeholder
- Built end-to-end: TLE fetch/cache (Celestrak) + skyfield pass prediction, SatNOGS ingestion + normalization + APScheduler, FastAPI dashboard/API
- Cross-validated pass prediction against an independent orbital library (pyephem) since n2yo.com's predictor isn't scriptable — AOS/LOS agreed within ~2-3 min
- Live smoke test: 25 real SatNOGS observations ingested end-to-end with full waterfall/audio/decoded-data coverage
- 14 automated tests written and passing (prediction, normalization, ingestion incl. outage handling, API/dashboard shape incl. empty states)
- All 6 acceptance criteria verified live, not just by test suite
- Ran full 7-auditor milestone-completion review: PROCEED, no blockers. Fixed all 4 real non-blocking findings same-session (ingest batch isolation, logging visibility, dependency pinning + count query + error sanitization, viewport meta)
- Wrote `prototype-notes.md` (grant-application writeup) and full doc set (API, architecture, changelog)
- Milestone marked COMPLETED, v1.0.0 logged

**Next**:
- Confirm GHRCE's exact station coordinates with the GHRCE team before grant submission
- Add minimal CI workflow (pytest on push) — logged as Milestone 2 debt
- Add `.env.example` + README run instructions before any live demo
- Decide on Milestone 2 scope with Abheejit (candidates: CI/lint setup, GHRCE coordinate confirmation, longer soak-test of the scheduler)

**Decisions**: Kept `app/ingest.py`'s in-memory ingestion timestamp alongside `status.py`'s DB-derived one rather than deleting — documented which is authoritative for what (Arjun's finding), since tests depend on the former and AC4 requires the latter.

**Resume**: <!-- RESUME: Milestone 1 is COMPLETED and merged to milestone/1-mvp-prototype branch (not yet merged to main — confirm with Abheejit before merging). Start next session by proposing Milestone 2 scope. -->
<!-- End of session log -->
