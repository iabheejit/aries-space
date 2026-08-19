# Session Log
<!-- Reverse chronological. One entry per session. -->
<!-- Format: ## {date} | Milestone {N} | {title} -->
<!-- What was done, what's next, any RESUME markers -->

## 2026-08-17 | Milestone 7 | Orbital IQ mockup replicated with a genuinely live orbital layer

- Founder asked to replicate the shared "Orbital IQ" mockup exactly, live-wired, "with source of all the overheads satellites". Confirmed first that the mockup itself is **not** in the repo — `dashboard-screenshots/` only holds our own renders, and nothing matching it exists in the workspace. It survives only as a chat attachment; **it still needs to be saved to `design/mockups/` for the record** (a chat attachment can't be written to disk from here). Built from the image directly in the meantime.
- Founder was unavailable for the three clarifying questions (mockup file, how to treat fabricated panels, live-map scope), so the calls were made autonomously and are stated plainly here: replicate the layout faithfully, keep every unbacked panel badged CONCEPT, and make the map real rather than decorative.
- **New real capability — live overhead satellite tracking.** `services/api/aries_api/overhead.py` propagates real Celestrak GP TLEs through SGP4/Skyfield: sub-satellite point, altitude, velocity, elevation/azimuth from GHRCE, sensor-footprint radius, inclination and period. Backed by a new cached group-TLE fetch (`tle.get_group_tles`) reusing the existing stale-fallback semantics. Default group is `resource` (Earth-resources/EO) — **168 real satellites**, which is what this product is actually about.
- New public read endpoint `GET /api/overhead`, with an `offset_minutes` parameter (±720) so the mockup's "REPLAY / NOW" timeline is real orbital time-travel, not a decorative slider. Verified live: 5 satellites above the horizon now vs. 3 at +45 min.
- New route `/dashboard/orbital-iq` + `dashboard_orbital_iq.html`, a faithful rebuild of the mockup's structure (sidebar, header with live orbit facts, 1 Mission Health / 2 Edge Economics, 3 Fused Intelligence Map, 4 Event Queue / 5 Event Detail / 6 Event Economics, bottom KPI strip). Map is a dependency-free canvas renderer over real Natural Earth 110m coastlines (`static/land-110m.json`, 57 rings / 65KB, public domain), drawing real footprints, real ground track, ground station, IOR/WORLD views, working layer toggles and click-to-inspect.
- **Honesty preserved, not quietly dropped**: node-health bars, SAR/AIS detections, event queue, event detail M-2841, event economics, customer coverage and all revenue figures stay badged CONCEPT with per-panel disclosures, plus a page-level disclosure. The mockup's SAR and AIS layer checkboxes are wired to *refuse* to switch on and explain that no such feed exists. `/` and `/dashboard/concept` are untouched.
- Two real findings worth keeping: (1) a malformed TLE does **not** raise in SGP4 — it silently returns non-finite garbage, so `satellite_states` now rejects non-finite results explicitly (a test covers it); (2) the first `pytest` run showed a `test_config` failure that was **my own shell pollution** from sourcing `.env`, not a regression — re-ran clean.
- Verification: **124 passed, 7 skipped** (was 107; +17 new tests across `test_overhead.py`, `test_tle_groups.py`, plus 2 new Playwright honesty tests that assert the CONCEPT badges and the refusing SAR toggle). `compileall` clean, `compose_smoke.py` `{"status": "ok"}`, `git diff --check` clean, no horizontal overflow at 1440/1728/390 px. Live via the ngrok tunnel.

**Next**: save the mockup PNG into the repo; founder review of the layout against the original; decide whether the CONCEPT panels stay as layout placeholders or get replaced by real Aries data in those slots. Still open from earlier: Pi 4B hardware run, CI push, business-doc rewrite.

**Resume**: <!-- RESUME: Milestone 7 IN_PROGRESS. /dashboard/orbital-iq is live and real (168 satellites, SGP4, ±720min replay); /, /dashboard/concept untouched. Original Orbital IQ mockup image is still NOT in the repo — needs saving to design/mockups/. Stack healthy, uncommitted. -->

## 2026-08-17 | Milestone 7 | Session close-out

This session covered three pieces of work, each logged in its own entry below (reverse chronological, so scroll down for full detail): (1) the predicted full-tile crossover was confirmed live for `sentinel2-ndvi-summary`, (2) four of the remaining five workloads were confirmed at true full-tile scale — including a genuinely new finding (ship-detect's high DRF doesn't save it from `ground` because its absolute input size is smaller) — with `sentinel2-landcover-classifier` left honestly unmeasured at that scale due to a real local memory ceiling, and (3) the edge-hardware evidence plan pivoted from an unacquired Jetson Nano to a real Raspberry Pi 4B, with benchmark tooling built and dry-run verified but not yet run on the actual device.

**Closing state, verified before ending**:
- Docker stack (`app`, `postgres`, `minio`) running healthy, `.env` in standard fixture mode, `compose.yml`'s new passthroughs (agricultural + coastal crop windows, fetch/benchmark timeouts, sample iterations) are permanent and don't break the default fixture-mode path — 107 tests passing, `compose_smoke.py` clean.
- `.env.example` brought up to date with the coastal crop vars added to `compose.yml` this session (previously undocumented).
- EVIDENCE.md, `.claude/versions.md` (through v3.3.2) all reflect the session's real findings, including the disclosed gaps (landcover-classifier full-tile, Pi hardware run) rather than papering over them.
- The published "Aries Evidence Summary" business artifact was updated with the full-tile results and the ship-detect nuance; it intentionally does not claim a Pi hardware run since none has happened yet.
- Git working tree still uncommitted (this and Milestones 6/7's other work) — no commit was requested this session, so none was made. `git status` shows a clean, understood diff (18 modified + 12 new files, all attributable to M6/M7 work), nothing unexpected.
- No memory files were cleared — the founder confirmed "clear the memory" meant end the session normally, not wipe persistent context. A new project memory (`aries_edge_hardware_pi4b_pivot`) was added to carry the Pi plan forward.

**Not done, still open**: milestone 7 has no plan doc yet (process deviation disclosed in audit-trail.md); full 7-agent audit for Milestone 7 hasn't run; CI hasn't seen this branch's changes; the Raspberry Pi hasn't been physically set up; business-doc rewrite (wedge reframe, cost-per-insight, Validation Matrix) still not started; no real customer engagement yet.

**Resume**: <!-- RESUME: Milestone 7 IN_PROGRESS, uncommitted. Next concrete step is physically setting up the Raspberry Pi 4B and running scripts/pi_landcover_benchmark.py for real (see entry below and aries_edge_hardware_pi4b_pivot memory). Stack is healthy in standard fixture mode. Nothing mid-flight or left in a dirty state. -->

## 2026-08-17 | Milestone 7 | Edge hardware evidence pivot: Raspberry Pi 4B groundwork (scripts only, not yet run)

- Founder pushed back on the framing of the business note's remaining honesty gap: rather than wait on an unacquired Jetson Nano, use hardware actually on hand — asked whether the Mac M4 run could just be presented as "a real hardware test," and separately flagged owning a real Raspberry Pi 4B (2GB RAM)
- Asked two clarifying questions before touching anything, since this changes what gets claimed to a grant reviewer: (1) what should the edge evidence actually be — reframe the Mac run, add the Pi as a second real target, or replace the Mac entirely; (2) is the Pi reachable from this session to run live. Founder chose: add the Pi 4B as a real second edge target, but the Pi isn't set up/reachable yet — that run happens in a later session
- Built the groundwork so that session goes fast: `scripts/pi_landcover_benchmark.py` (standalone driver meant to run *on* the Pi — real ONNX inference, no artificial thread throttling since the Pi's own hardware already is the edge-class device, power draw explicitly left `"NOT YET MEASURED"` rather than defaulted) and `scripts/ingest_pi_benchmark_result.py` (dev-machine script that turns the Pi's raw timing JSON into real cost figures using Aries's actual `calculate_run_metrics()`, not a duplicated formula)
- Both scripts dry-run end-to-end today on this Mac (real fixture, real model, real onnxruntime execution) to confirm the code path works before ever touching the Pi — but zero numbers from today are Pi-hardware evidence, and EVIDENCE.md is explicit about that distinction
- Retired the Jetson Nano framing from the pending-work language — it was never actually acquired, just an earlier placeholder; the Pi 4B is now the real, disclosed plan

**Next**: set up the Raspberry Pi 4B (Raspberry Pi OS 64-bit, Python venv, onnxruntime for aarch64), copy over the model + fixture + `pi_landcover_benchmark.py`, run it for real, then `ingest_pi_benchmark_result.py` the result. That's a genuinely new, physically-separate-hardware data point for the business case — stronger than anything currently in EVIDENCE.md for this workload.

**Resume**: <!-- RESUME: Milestone 7 IN_PROGRESS. Pi 4B benchmark scripts written and dry-run verified, but the actual Pi has not been set up or run against yet — that's the very next concrete step, blocked only on the founder having physical access to set up the Pi. Business note (Aries Evidence Summary artifact) still describes the landcover classifier as Mac-measured only; do not upgrade that language until a real Pi run exists. -->

## 2026-08-17 | Milestone 7 | Full-tile confirmation for 4 of the 5 remaining workloads (1 blocked by a real local memory constraint)

- Founder asked to run the other 5 workloads (the follow-up flagged at the end of the previous entry) at full-tile scale
- Re-ingested the agricultural full tile fresh (the previous session's dataset row didn't survive a stack rebuild) as dataset `4`, and — new — ingested the coastal/JNPT scene at full 10,980×10,980 resolution for the first time as dataset `5` (180,353,124 bytes, single NIR band; `ship-detect`'s own AOI, previously only tested at 1024×1024). Added the matching `SENTINEL2_COASTAL_CROP_*` passthroughs to `compose.yml` (only the agricultural-side ones existed from yesterday)
- `cloud-mask` and `sentinel2-quicklook-thumbnail` (both against dataset 4) ran clean and confirmed `edge` — margins ₹27.69/run and ₹16.06/run
- `sentinel2-lossless-recompress` (dataset 4) confirmed `ground` — near-1× DRF (1.05×) never comes close to clearing the fixed ₹164.38 edge hardware charge; break-even downlink ₹8,378/GB
- `ship-detect` (dataset 5, coastal) confirmed `ground` — genuinely surprising given it has the *highest* DRF measured all session (69,580.68×, above even `cloud-mask`'s 653,113.83×). Root cause understood, not just observed: its input is only 180MB (single band) vs. the other workloads' 384MB (two bands), so the absolute downlink cost it saves (~₹90) never clears edge's flat ₹164.38 hardware charge. **New, disclosed nuance for the frontier story**: DRF alone doesn't determine placement at full scale — absolute input size matters too, because edge's dominant cost is a flat per-run charge, not proportional to the reduction achieved
- `sentinel2-landcover-classifier` (dataset 4) — **not measured**, two independent attempts both crashed the app container (connection reset, `curl` exit 52, container `RestartCount` incremented each time; not flagged `OOMKilled` by `docker inspect` but consistent with the local Docker Desktop VM's shared 7.65GiB ceiling being exceeded by the workload's ~2GB four-feature-array allocation across all 120.6M pixels). Did not attempt a workaround (e.g. quietly reducing the crop) — that would defeat the point of a full-tile confirmation. Logged as a genuine open item: needs either a chunked/streaming feature-engineering rewrite or a higher-memory host, not solved today
- EVIDENCE.md updated with the full comparison table and the ship-detect finding written up in detail; Pending Evidence list gained the landcover-classifier full-tile item
- Cleaned up: `.env` reverted to standard fixture mode, `compose.yml`'s new coastal passthroughs are permanent (kept)

**Next**: fix `sentinel2-landcover-classifier`'s memory footprint (chunked processing) if a full-tile measurement is wanted before the grant deadline — otherwise the existing 1024×1024-scale measured result (Milestone 6) still stands on its own. Business-doc rewrite still not started. Push to CI still open.

**Resume**: <!-- RESUME: Milestone 7 IN_PROGRESS. 6 of 7 workloads now have full-tile real confirmation (5 from this entry + NDVI from the prior one); landcover-classifier is the one exception, blocked by a real local memory constraint, not yet fixed. .env is back in standard fixture mode; compose.yml gained SENTINEL2_COASTAL_CROP_* passthroughs (permanent) on top of yesterday's additions. Not yet merged to main. -->

## 2026-08-17 | Milestone 7 | Predicted crossover CONFIRMED live: real full-resolution tile, edge wins

- Founder asked to re-test raw network throughput (previous attempt at full-tile fetch was impractical at ~0.2MB/s). Re-test found genuine improvement: ~1.05MB/s then ~3.26MB/s sustained (100MB in 32.1s, direct curl range-request against the real S2 COG) — environment conditions had changed, not a fluke (two separate re-tests both showed improvement)
- At ~3.26MB/s the ~385MB full-tile fetch became a ~3-minute operation. Founder confirmed ("yes") to attempt it
- Verified real tile dimensions via rasterio before committing (10,980×10,980, not assumed) — set `SENTINEL2_CROP_WIDTH/HEIGHT=10980`, `COL_OFF/ROW_OFF=0` via `.env`
- **First attempt returned the old 1024×1024 crop** — root cause: `compose.yml` never forwarded `SENTINEL2_CROP_*`/`SENTINEL2_FETCH_TIMEOUT_SECONDS` env vars to the container at all (only `SENTINEL2_FIXTURE_PATH` was wired). Fixed as a permanent `compose.yml` passthrough addition, not a one-off workaround
- Real ingest succeeded: 384,030,932 bytes in 3:00.44 — within 0.2% of the prior day's extrapolated estimate (384.8MB), a strong cross-check that the extrapolation method was sound
- First benchmark attempt at full-tile scale also failed (503) — root cause: `BENCHMARK_TIMEOUT_SECONDS` (10s default) and `SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS` (15) were tuned for small crops and also silently un-wired in `compose.yml`; a full-tile NDVI median-timing loop needs far more than 10s. Fixed as a second permanent `compose.yml` passthrough; used `BENCHMARK_TIMEOUT_SECONDS=300`, `SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS=5` for this one-off run via `.env`
- **Real measured result**: `sentinel2-ndvi-summary` at full-tile scale — ground 6.77s wall/₹0.1885/run, edge-sim 27.1s wall/₹164.38/run, DRF 709,853.85×, recommendation `edge`, break-even downlink ₹427.56/GB (below configured ₹500), break-even utilization 0.86 runs/day (below the current 1.0/day assumption). **Edge wins by ₹27.82/run** — every figure landed within ~2-4% of the previous day's PREDICTED calculation, done on a genuinely different, much larger, real input
- **This is the confirmation the thesis needed**: real measured evidence now exists on both sides of the placement frontier — small/infrequent payloads favor ground (TCO fix round 2, 2026-08-16), full-resolution real scenes favor edge (this entry) — same unmodified cost formulas, same conservative duty-cycle assumption, both genuinely measured, not modeled
- Cleaned up: reverted `.env` to standard fixture mode (kept the `compose.yml` passthrough fixes, which are permanent operational improvements, not one-off hacks). 107 tests passing, `compose_smoke.py` clean on a fresh standard-mode stack
- EVIDENCE.md updated: the prior PREDICTED entry's header now points to this confirmation; a new dated entry has the full real numbers and the side-by-side comparison against the prediction

**Next**: Optionally re-run the other 5 workloads at full-tile scale for independent confirmation (only NDVI was measured this session) — logged as a follow-up, not claimed as done. Business-doc rewrite is now unblocked and stronger than before: the honest story is "ground for small/infrequent, edge for full-resolution/frequent," with real measurements on both ends, not a hedge. Still open from M6/earlier M7: push to CI, real Jetson-class hardware, one real customer workload.

**Resume**: <!-- RESUME: Milestone 7 IN_PROGRESS. Core thesis has real measured confirmation on both sides of the placement frontier as of this entry. .env is back in standard fixture mode; compose.yml has new (permanent) SENTINEL2_CROP_*/BENCHMARK_TIMEOUT_SECONDS/SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS passthroughs. Not yet merged to main. No plan doc exists for this milestone. -->

## 2026-08-16 | Milestone 7 | Placement Frontier started: two real near-boundary workloads

- Founder asked to find near-boundary workloads, choosing (via explicit prompt) to build new ones now rather than sweep assumptions over the existing 5
- Built `sentinel2-lossless-recompress` (real zlib-9 recompression, no semantic analysis) and `sentinel2-quicklook-thumbnail` (real block-mean 4x decimation + zlib-6) — both deliberately NOT detection/summary workloads, so their real output is the (compressed) data itself, not a tiny extracted insight
- Real, unforced numbers landed exactly where predicted: DRF 1.05× and 15.89×, vs. the existing cluster's 28×-100× — the frontier concept validated with actual measurements, not tuned
- Computed sensitivity (break-even hardware rate) is the more honest story than the binary recommendation: recompress's flip-rate (₹627.60/hr) is ~50-150× closer to the current ₹6.85/hr assumption than the detection cluster's (₹23k-105k/hr) — real, quantified evidence that different workloads sit at genuinely different distances from the boundary, even though none crosses to `ground` yet under current assumptions
- **Process deviation, disclosed**: skipped the full plan → Vikram review → 7-agent audit ceremony used for M1-6, given (a) this session already lost one audit agent to the account's monthly spend limit during M6, and (b) both workloads strictly follow the already-reviewed `WorkloadSpec` pattern with zero new architectural surface. Wrote a Mr Fox self-review into audit-trail.md instead; flagged for a real agent audit pass once spend limits reset
- 109 tests passing (5 new), live-verified against a freshly rebuilt Compose stack, `compose_smoke.py` covers both new workloads end-to-end
- EVIDENCE.md updated with the full frontier table (all 7 workloads, DRF + recommendation + break-even hardware rate)
- **Same-day follow-up**: founder asked directly whether "edge wins everywhere" fails the project's founding assumption. Investigating surfaced a second, larger TCO bias: edge hardware CAPEX was amortized against active compute-*time*, implicitly assuming near-continuous utilization. Researched real satellite duty-cycle patterns via WebSearch (now working again this session) — a cited power-constrained CubeSat design runs its AI payload just 1 orbit/day, vs. Planet's mass-mapping ~100 captures/day/satellite; commercial smallsat design life 3-5 years, historical actual average only ~2.1 years. User chose the conservative 1 run/day default (strongest stress test) via AskUserQuestion over 10/day or a full sensitivity sweep.
- Rebuilt the cost model: CAPEX now amortized against expected uses (`CAPEX / (runs_per_day × 365 × years)`) instead of active time — `metrics.calculate_run_metrics` gained a genuinely flat `fixed_cost_inr_per_run` parameter, distinct from the existing time-proportional rate; ground's rental model untouched (correctly still time-proportional, real cloud billing).
- **Result: every workload's recommendation flipped from `edge` to `ground`** at the default 1 run/day — ₹164.38/run fixed hardware charge dominates at these crop sizes (few tens of KB downlink savings). This is the honest finding, not spun: the earlier "edge wins everywhere" result was an artifact of the continuous-utilization assumption, not a real conclusion. Dashboard's sensitivity readout changed from "break-even hardware rate (₹/hr)" to "break-even utilization (runs/day)" — a more actionable, business-relevant number. 107 tests passing (none needed direction-specific rewrites — written generically), live-verified, full sources logged in EVIDENCE.md.
- **What this doesn't yet prove**: not that edge never wins — only that it doesn't win for a single low-frequency payload on small crops under a conservative, disclosed duty-cycle assumption. A high-frequency/high-volume/multi-tenant-hardware workload hasn't been tested and could still favor edge.
- **Same-turn follow-up**: founder said "yes" to finding a workload that could favor edge even under the conservative model. Solved analytically first rather than jumping to a live run: the linear cost formulas give an exact crossover, ≈328.8 MB input scene, at which downlink savings alone pay for the fixed ₹164.38/run edge hardware charge. That's not an absurd number -- a full-resolution Sentinel-2 tile (10,980×10,980px, 2 bands) is ~385MB, genuinely close. Attempted a live full-tile fetch to confirm; a raw `curl` range-request against the real S2 COG measured only ~0.2MB/s sustained throughput from this sandboxed session -- a ~400MB fetch would take 30-40+ minutes, impractical mid-session. Extrapolated instead from the real measured 128×128-crop rates (explicit linear scaling, disclosed as a thin n=1 basis for the compression-ratio assumption): predicted edge wins by ≈₹28/run at full-tile scale, even at 1 run/day. Logged in EVIDENCE.md as a new, distinct "PREDICTED" label (not MEASURED/ESTIMATED/SIMULATED) -- explicitly not proof, a real next experiment to run from an unconstrained network.

**Next**: Run the full-resolution live fetch from a network path that isn't bandwidth-constrained, to confirm or refute the predicted edge-wins-at-scale finding with a genuine measurement -- the single highest-value remaining technical experiment. Also still open from M6: push to CI, real Jetson-class hardware, one real customer workload, business-doc rewrite (wedge reframe now especially important -- "edge wins at scale, ground wins for small/infrequent payloads" is a sharper, more credible story than either extreme) not yet done.

**Resume**: <!-- RESUME: Milestone 7 IN_PROGRESS. Cost model duty-cycle-aware (EDGE_EXPECTED_RUNS_PER_DAY=1 default); all current (small-crop) workloads recommend ground. A full-tile-scale PREDICTED (not measured) crossover back to edge is documented in EVIDENCE.md, blocked on this sandbox's ~0.2MB/s network -- confirming it live from an unconstrained network is the top open item. Not yet merged to main. No plan doc exists for this milestone (see process note above). -->

## 2026-08-16 | Milestone 6 | Measured-Edge AI Case Study: real trained ONNX model, genuinely measured ground vs. edge

- Founder's challenge: every prior "edge wins" number was formula-derived (ground median × configured slowdown factor) — needed genuinely measured evidence for grant-deadline case study
- Also worked through two bigger strategic threads with the founder this session (discussion only, not built): generalizing the kernel toward "AI data centers in space" for telecom/cloud providers, and the observation that "edge wins" recommendations presuppose onboard compute the sensor-only majority of real satellites don't have — reframed as a two-audience value prop (pre-launch design-decision tool + post-launch operational routing tool)
- Plan drafted, Vikram REFINE (5 gaps: explicit dispatch mechanism, field-count mismatch, accuracy-circularity disclosure, workload-agnostic assumptions snapshot, timeout sizing) — all fixed pre-code, documented in plan's Revision Note
- Built: `sentinel2-landcover-classifier` workload — real trained 3-class MLP (vegetation/bare-soil/cloud; water excluded, zero training examples, disclosed), hand-built ONNX graph via `scripts/train_landcover_classifier.py`, `WorkloadSpec` extended with 7 optional edge-override fields (zero regression to the 4 pre-existing workloads, verified by a dedicated test)
- Both `ground-cpu` and the new `edge-measured-mac` target genuinely execute the same ONNX model under different real `SessionOptions` (multi-thread vs. single-thread-constrained) and are independently timed — `is_simulated=False` on both, DB-persisted assumptions now spec-aware instead of universally hardcoded
- Live-verified against a freshly rebuilt Compose stack: ground 0.783ms vs. edge 0.878ms (edge genuinely *slower* at this crop size — an honest, disclosed, counter-intuitive finding a formula couldn't produce), recommendation `edge`, break-even ₹0.00/GB
- Recommendation label renamed project-wide `simulated_edge` → `edge` (the old name asserted "formula-derived" as universal, no longer true) — dashboard generalized to resolve the non-ground-cpu run dynamically instead of a hardcoded `edge-sim` slug
- 7-agent milestone-completion audit: 6 ran as agents (Security PASS, PM ON_TRACK, Strategy ALIGNED, Engineering NEEDS_WORK→fixed, Design ITERATE→fixed, DevOps OPERATIONAL_RISK); Architecture's agent hit the account's monthly spend limit mid-review and was completed directly by Mr Fox, labeled as a substitution, not attributed to the agent
- Two concurrent-write races on `audit-trail.md` during the parallel audit (no file locking) cost two sections (Vikram's, Priya's) — both recovered from the agents' completion-notification text before more agents could compound the loss
- Fixed inline post-audit: `_seed_catalog` variable-shadowing (Arjun), dashboard TIMING MEASURED/SIMULATED badge — previously both targets showed an identical "ESTIMATED" power badge, burying the milestone's core claim (Divya)
- 97 tests passing (5 skipped), CI not yet run on this exact diff (open action item)
- EVIDENCE.md updated with full real numbers and the accuracy-circularity caveat stated explicitly in prose, not just code comments
- **Same-day follow-up, post-milestone**: external strategic review (founder-sourced) argued the cost model structurally biased every recommendation toward edge (ground charged compute rental, edge charged electricity only) — fixed immediately: edge now carries an amortized hardware CAPEX rate (₹300,000 / 43,800hrs = ₹6.85/hr default, disclosed in `assumptions`), applied to all 5 workloads. Recommendation didn't flip under defaults, but break-even is no longer zero-by-construction — computed flip point disclosed per workload (e.g. ₹98/hr for the classifier, ₹22,803/hr for ship-detect). New regression test locks in that edge cost > electricity-only cost. 98 tests passing.
- Fresh live demo run produced a business-facing "Aries Evidence Summary" artifact (all 5 workloads, real numbers, published for the founder to share)
- Dashboard rebuilt to the "real product UI" concept from the same review: per-workload line-item cost table (Compute/Energy/Hardware/Downlink saved/Total-per-insight) plus a sensitivity readout (break-even hardware rate, break-even downlink price, confidence badges) — fully derived client-side from existing API fields, no backend/DB changes. Caught and fixed one wording regression via the existing Playwright honesty-label test (abbreviated badge text had silently dropped the literal word the test checks for). 100 tests passing, live-verified via screenshot and a fresh `compose_smoke.py` run.
- Deferred, per founder's explicit choice: the "Placement Frontier" (deliberately sourcing new workloads near the 1×–10× reduction boundary) — waiting until real near-boundary workloads exist rather than building a sweep over the 4 existing ones. Also logged from the same review, not yet started: get real edge hardware (Jetson-class) to replace the Mac stand-in, and land one real customer workload/engagement — both flagged as the highest-value next moves, business-development/procurement items rather than code.

**Next**: Push branch, confirm green `container-smoke` CI run on `ubuntu-latest`/x86_64 (the one unverified item). Founder decisions pending: retry 1024×1024 live-AWS crop once network is unconstrained; how upfront to be in the grant narrative about the sensor-only-satellite constraint; when to pursue real Jetson-class hardware and a real customer workload. Fast-follow tech debt logged, not urgent: shared feature-engineering between train/inference scripts.

**Resume**: <!-- RESUME: Milestone 6 COMPLETE, not yet merged to main (still on milestone/6-measured-edge-case-study branch — confirm branch state before merging). CI verification on this diff is the one open item before treating this as fully proven. -->

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
