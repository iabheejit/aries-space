# Milestone 1: MissionOps Lite — Working Prototype
**Created**: 2026-08-15 | **Target**: 2026-08-19 | **Project**: MissionOps Lite (aries-space)

## Objective
Ship a working satellite mission-ops prototype — pass prediction, real telemetry ingestion from SatNOGS, normalization, SQLite storage, dashboard, and API — that demonstrates TRL 4→6 validation for the DoT/TCOE India Pilot Grant application, using only real satellite data (Celestrak TLE + SatNOGS Network API).

## Acceptance Criteria
1. `GET /api/passes?count=N` (default N=5) returns the next N upcoming passes for the configured NORAD ID and GHRCE ground station coordinates (start, end, max elevation, direction), computed from a live TLE pulled from Celestrak — verified by running the endpoint and cross-checking one pass window against an independent source (e.g. n2yo.com or Heavens-Above) with AOS/LOS times matching within ±5 minutes.
2. At least 1 real observation record for the chosen satellite has been pulled from the SatNOGS Network API and persisted to SQLite (`observations` table) with the raw JSON payload intact — verified by querying the DB directly.
3. At least 1 observation has been normalized into the structured schema (`timestamp`, `satellite_id`, `station_id`, `frequency`, `signal_quality`, `waterfall_url`/`audio_url`, `decoded_data`) — verified by asserting the normalized record appears as a row in the dashboard's rendered HTML response (`GET /` response body contains the expected fields), not by manual eyeballing.
4. `GET /api/status` returns real, non-stub values: observations ingested in last 24h (computed from DB rows), last successful ingestion timestamp (from DB, not `datetime.now()`), and satellite/station currently configured.
5. `GET /` returns HTTP 200 and the rendered HTML body contains all four named sections (satellite+station info, upcoming passes table, recent observations table, mission health summary), each backed by live API data with no hardcoded placeholder rows — verified via response-body assertions in `test_api.py`. Empty-state case (no passes/observations yet on first run) is a testable sub-case: dashboard still returns 200 with an explicit "no data yet" indicator per section, not an error or blank crash.
6. A written note (`.claude/docs/prototype-notes.md` or similar) captures: satellite tracked, real observation count ingested, what worked, what remains manual/unfinished — ready to paste into the grant's "Details of Working Prototype" field.

## Approach
- **Satellite selection**: query SatNOGS `/api/satellites/` + `/api/observations/` for an actively-tracked, well-documented satellite with frequent recent observations (favor data availability — e.g. a common cubesat like NORBI, FossaSat, or similar with high observation counts). Confirm choice against live API data before building around it, not from prior knowledge.
- **GHRCE coordinates**: use publicly known GHRCE (Nagpur) approximate coordinates as a placeholder (~21.12°N, 79.04°E, ~310m elevation); flag as an assumption to be confirmed by Abheejit with GHRCE's actual SatNOGS station record if one exists (`/api/stations/` filtered by name/location) — prefer that station's registered lat/lon if found.
- **Pass prediction**: `skyfield`, TLE fetched live from Celestrak (`https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE` or similar current Celestrak endpoint), cached with a refresh interval (TLEs go stale after ~days).
- **Ingestion**: `httpx` polling SatNOGS `/api/observations/?satellite__norad_cat_id={id}` on a schedule via `APScheduler`; store raw JSON as-is in `observations.raw_json`, then a normalization step populates the structured columns.
- **Storage**: SQLite via `sqlmodel`, two tables (`passes`, `observations`) per spec; binary artifacts (waterfall/audio) stored by URL reference only.
- **API + Dashboard**: FastAPI backend serving JSON endpoints + a Jinja2-rendered single-page dashboard (fastest to stand up, matches spec's "no design polish needed").
- **Risk**: SatNOGS may have zero recent observations for whichever satellite is picked if it's gone quiet — build the satellite-selection step to actually check live data first, not assume.
- **Outage handling**: if Celestrak is unreachable at request time, `/api/passes` serves the last successfully cached TLE (with a `stale: true` / cached-age flag in the response) rather than a 500; if no TLE has ever been cached, return a clear 503 with a descriptive error, not a stack trace. If SatNOGS polling fails, the scheduler logs the failure, leaves `last_successful_ingestion` unchanged, and retries on the next interval — it does not crash the app or corrupt existing rows. Both cases get at least one test in `test_predict.py` / `test_api.py` using a mocked failure.
- **SatNOGS polling etiquette**: poll on a fixed interval no tighter than every 5 minutes (`OBS_POLL_MINUTES` default 10) with a single in-flight request at a time (no concurrent polling), consistent with being a well-behaved consumer of a public API with no key/rate-limit contract.

## Execution Sequence
Given the subsystem count in a 4-day window, work proceeds in three sequenced phases within this single milestone (not separate milestones — the acceptance criteria only make sense together as one demoable prototype):
1. TLE fetch/cache + skyfield pass prediction + `/api/passes` + `test_predict.py`
2. SatNOGS ingestion + normalization + scheduler + `test_normalize.py`
3. Dashboard + `/api/status` + `test_api.py` + `prototype-notes.md`
If phase 1 or 2 overruns significantly, the milestone can still be marked COMPLETED on a reduced scope (e.g. fewer observations, manual-trigger ingestion instead of full scheduler) as long as all six acceptance criteria are still met — that's a scope-reduction decision for Abheejit, not silent scope cut.

## Files Affected
- `app/main.py` — FastAPI app, routes
- `app/db.py`, `app/models.py` — SQLModel schema (`Pass`, `Observation`)
- `app/tle.py` — Celestrak TLE fetch + cache
- `app/predict.py` — skyfield pass computation
- `app/ingest.py` — SatNOGS polling + raw storage
- `app/normalize.py` — raw → structured mapping
- `app/scheduler.py` — APScheduler jobs (refresh passes, poll observations)
- `app/templates/dashboard.html` — Jinja2 dashboard
- `app/config.py` — NORAD ID, station coords, poll intervals (env-var driven)
- `requirements.txt`
- `.claude/docs/prototype-notes.md` — grant writeup

## Tests Required
- `test_predict.py`: given a known TLE fixture, pass computation returns expected pass count/ordering for a fixed time window (deterministic, not live-network dependent).
- `test_normalize.py`: given a sample raw SatNOGS observation JSON fixture, normalization produces correct structured fields, including graceful handling of missing optional fields (no decoded_data, no waterfall).
- `test_api.py`: `/api/status` returns real DB-derived counts (seed test DB, assert values match); `/api/passes` and `/api/observations` return well-formed JSON with expected shape.
- One manual/live-integration check (documented, not automated): live Celestrak fetch + live SatNOGS ingestion pull actually succeeds end-to-end — captured in the prototype notes, not a CI test (avoids flaky network-dependent test suite).
- Outage-handling tests (mocked failures, per Approach): `test_predict.py` covers `/api/passes` serving cached TLE with `stale: true` when Celestrak is unreachable, and a clean 503 when no cache exists yet; `test_api.py` or `test_ingest.py` covers the scheduler leaving `last_successful_ingestion` unchanged and not crashing when a SatNOGS poll fails.

## Out of Scope
- Live RF/SDR reception or hardware control
- Multi-ground-station orchestration or routing logic
- AI/anomaly detection features
- User authentication or multi-tenant support
- Production deployment/infra hardening
- Writing new RF decoders — surface SatNOGS-provided decoded data as-is only

## Dependencies
- Network access to celestrak.org and network.satnogs.org (no API key required for either as of spec).
- Confirmation from Abheejit on GHRCE's exact station coordinates if a more precise source than public approximation is available.
- Python 3.11+ environment for skyfield/FastAPI/sqlmodel.

## Design Considerations
Single Jinja2-rendered page, functional only per spec (no design polish required). Divya's audit should focus on: is the mission-health summary legible at a glance, are empty states handled (no passes yet / no observations yet on first run before scheduler has run), and is the raw-data link from the observations table actually usable (opens to real payload, not broken).

## Security Considerations
- No secrets or API keys required — both Celestrak and SatNOGS public endpoints are keyless per this spec; if that changes (e.g. a SatNOGS API token becomes required), it goes in an env var, never in code or committed config.
- No user-facing write endpoints and no auth in this milestone (explicitly out of scope) — all FastAPI inputs are either env-var-driven config (not request-supplied) or read-only query params (`count` on `/api/passes`, pagination params on `/api/observations`); those get basic type/range validation via FastAPI/pydantic to avoid unbounded or malformed queries, not because they're an auth boundary.
- SQLite file lives on local disk with default filesystem permissions — acceptable for a single-operator prototype with no multi-tenant data; not revisited until a real pilot deployment.
- Raw JSON payloads and any waterfall/audio URLs stored from SatNOGS are treated as external, untrusted data on render (no `|safe`/unescaped HTML injection in Jinja2 templates).

## Operational Considerations
- Env vars: `NORAD_ID`, `STATION_LAT`, `STATION_LON`, `STATION_ELEV_M`, `TLE_REFRESH_HOURS`, `OBS_POLL_MINUTES`, `DB_PATH`.
- SQLite file needs a persistent path outside any ephemeral container layer if deployed; for prototype, local file is acceptable.
- Scheduler runs in-process (single instance assumption) — fine for prototype scale, Sanjay should flag if this needs to change before any real pilot deployment.
- No auth, no TLS assumptions — prototype only, consistent with explicit out-of-scope.

## Fundability / Demo Value
This is the primary working-prototype evidence for the DoT/TCOE Pilot Grant "Details of Working Prototype" field — directly demonstrates TRL 4→6 progression (integrated system components validated with real data, not lab-only synthetic data). The end-of-milestone written note is itself a grant-application deliverable, not just internal documentation.
