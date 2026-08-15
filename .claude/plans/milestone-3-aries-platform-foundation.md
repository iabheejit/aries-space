# Milestone 3: Aries Storage Foundation
**Created**: 2026-08-15 | **Target**: 2026-08-19 | **Project**: Aries Stage 0

## Objective
Cut MissionOps over to one PostgreSQL-backed FastAPI application and prove one real SatNOGS observation can be stored idempotently as MinIO raw data plus searchable PostgreSQL provenance.

## Acceptance Criteria
1. `docker compose up --build --wait --wait-timeout 120` starts exactly three required services: PostgreSQL 15, MinIO, and one FastAPI application. Images are pinned to immutable versions or digests, ports bind to `127.0.0.1`, containers have health checks, and `docker compose ps` reports all three healthy within 120 seconds on the M4 development machine. Startup creates `raw`, `processed`, and `results`; bucket assertions show only `raw` contains the milestone's ingested object.
2. `alembic upgrade head` creates PostgreSQL tables for MissionOps observations and Aries datasets. A dataset requires `source`, `external_id`, `observed_at`, `size_bytes`, `object_key`, `sha256`, and `ingested_at`; `satellite_norad_id` and `aoi_id` are nullable, with a check constraint requiring at least one. `(source, external_id)` and `object_key` are unique. An isolated migration test completes `upgrade head`, `downgrade base`, then `upgrade head` again.
3. The cutover has one ASGI entrypoint, one scheduler owner, zero runtime imports from the legacy `app` package, and zero SQLite reads or writes. Reusable TLE, prediction, normalization, status, and ingestion logic lives under `services/api/aries_api`; the legacy `app` directory is removed only after equivalent tests pass.
4. Existing MissionOps behavior remains available through `/`, `/api/passes`, `/api/observations`, `/api/status`, `/health/live`, and `/health/ready`. Contract tests assert the current response keys and bounds, the dashboard's four named sections and empty states, cached-TLE outage behavior, and DB-derived status. New API versioning and bearer authentication are deferred.
5. `POST /api/ingest/satnogs?norad_id=68635&limit=1` ingests exactly one available real SatNOGS observation and returns `201` with `dataset_id`, `external_id`, `object_key`, `size_bytes`, and `sha256`. The live script repeats the request as `POST /api/ingest/satnogs?norad_id=68635&observation_id={external_id}`, returns `200` with the same values, and leaves exactly one dataset row and one MinIO object. The manually gated live check is the only test that calls SatNOGS; offline tests use a captured real observation payload fixture.
6. Cross-store writes use a deterministic key `satnogs/{norad_id}/{observation_id}.json` and object-first ordering. If upload fails definitively, no row is committed. After an upload timeout, the application stats the deterministic key: an absent key fails with no row, an exact checksum/size match continues idempotently, and a mismatch fails without mutation. If row commit fails after a new upload, deletion is attempted; successful deletion leaves neither row nor object, while failed deletion emits a structured `orphan_object` error containing the bucket and key and returns 503 without a row. A pre-existing matching object is never deleted. Forced-failure integration tests prove each resulting row/object state and required log event.
7. `/health/live` returns `200 {"status":"alive"}` without touching PostgreSQL or MinIO. `/health/ready` checks both dependencies with a two-second timeout per dependency, returns `200 {"status":"ready"}` when both pass, and otherwise returns `503 {"detail":"Service is not ready"}`. Tests force PostgreSQL and MinIO failure independently and assert that logs contain the failed dependency name but no credentials.
8. `python -m pytest -q` and `python -m compileall -q services tests` pass offline. `python scripts/compose_smoke.py` completes within 180 seconds and deterministically proves health, migration state, one fixture-backed object/row pair, idempotent re-ingestion, checksum equality after download, and persistence after `docker compose up --detach --force-recreate app`; it does not call public upstreams.
9. Before cutover, `docker run --rm --user 0 --entrypoint python -v aries-space_missionops-data:/data:ro -v "$PWD/scripts/backup_sqlite.py:/backup_sqlite.py:ro" -v "$PWD/backups:/backup" aries-missionops:m2-rollback /backup_sqlite.py --source /data/missionops.db --destination /backup/missionops-m2.sqlite3` uses SQLite's online backup API and must print `integrity_check=ok`, `passes=<count>`, and `observations=<count>`. Any other result aborts cutover. Before source migration, the old image is tagged `aries-missionops:m2-rollback` and `ops/rollback/milestone-2.compose.yml` is validated to reference that image plus the existing `missionops-data` volume. Rollback uses `docker compose down`, then `docker compose -f ops/rollback/milestone-2.compose.yml up --detach --wait --wait-timeout 60`, followed by `curl --fail http://127.0.0.1:8000/health/ready` and assertions that `/api/status` row counts match the backup output. PostgreSQL writes made after cutover are not back-ported.
10. A fresh operator path is exactly: `cp .env.example .env`, `docker compose up --build --wait --wait-timeout 120`, then `python scripts/compose_smoke.py`. README sections cover prerequisites (Docker Desktop and at least 4 GB available memory), configuration, startup, live SatNOGS check, backup/restore, rollback, health checks, GHRCE's approximate campus coordinates, and milestone limitations.

## Approach
- Build the new application under `services/api/aries_api` and move proven MissionOps modules into it. Do not run old and new ASGI applications side by side.
- Use SQLAlchemy 2.x declarative models, psycopg, and Alembic. PostgreSQL becomes authoritative at cutover; the existing SQLite volume remains an immutable rollback/evidence artifact.
- Store raw SatNOGS payload bytes in MinIO's `raw` bucket and provenance in PostgreSQL. The application verifies SHA-256 before accepting a pre-existing object and compensates for a failed database commit only when it created the object in that attempt.
- Keep the existing Jinja dashboard and public route contracts for this milestone. This isolates storage migration risk from React and API redesign risk.
- Keep scheduler semantics (`max_instances=1`, coalescing, bounded HTTP calls, graceful shutdown) and one application worker.
- Use GHRCE's public campus pin (`21.1052484`, `79.0034903`) as an explicitly approximate default; exact antenna coordinates remain operator configuration.

## Cutover And Rollback
1. Stop Milestone 2 Compose without deleting `missionops-data`.
2. Build/tag `aries-missionops:m2-rollback`, validate `ops/rollback/milestone-2.compose.yml`, run the exact backup command from AC9, and retain the backup plus integrity/count output. Refuse cutover unless verification succeeds.
3. Start PostgreSQL, MinIO, and the new application; run migrations and the offline smoke test.
4. Run the manually gated one-observation SatNOGS check and record its object key, checksum, and dataset ID.
5. On failure, stop the new stack without deleting its volumes and restart the Milestone 2 definition against `missionops-data`. New PostgreSQL records are retained for diagnosis but are not synchronized to SQLite.

## Stage 0 Traceability
| Stage 0 requirement | This milestone | Later milestone |
|---|---|---|
| FastAPI, PostgreSQL 15, SQLAlchemy 2.x, Alembic | Foundation delivered | API expansion |
| MinIO `raw`, `processed`, `results` buckets | `raw` delivered; other buckets created | Processed artifacts and benchmark results |
| SatNOGS ingestion and idempotent provenance | One-observation vertical slice | Scheduled multi-satellite artifact ingestion |
| Mission pass scheduling and health alerts | Existing behavior preserved | React Mission view |
| Redis job queue | Explicitly excluded | Benchmark execution milestone |
| Sentinel-2 and watch-folder ingestion | Explicitly excluded | Ingestion expansion milestone |
| ONNX workloads and runners | Explicitly excluded | Workload and runner milestones |
| Metrics, Money Chart, and report | Explicitly excluded | Benchmark UI/report milestones |

## Files Affected
- `compose.yml`, `Dockerfile`, `.dockerignore`, `.env.example`, `README.md`
- `requirements.txt`, `requirements-dev.txt`, `alembic.ini`
- `services/api/alembic/`, `services/api/aries_api/`
- `tests/` fixtures and focused migration, repository, storage, ingestion, API, and readiness tests
- `scripts/backup_sqlite.py`, `scripts/compose_smoke.py`
- `ops/rollback/milestone-2.compose.yml`
- Legacy `app/` modules are removed only after their replacements pass equivalent tests

## Tests Required
- Existing fixed-TLE prediction, normalization, scheduler, API, dashboard, and outage tests run against the new package.
- Migration tests use an isolated PostgreSQL database and verify the named constraints and round trip.
- MinIO/PostgreSQL integration tests verify idempotency, checksums, object-first compensation, mismatch refusal, and persistence.
- Readiness tests prove independent dependency failures and bounded checks.
- Offline Compose smoke uses a captured real SatNOGS payload; a separate manually gated live check records current upstream evidence.

## Out of Scope
- Redis or any job worker
- Sentinel-2 ingestion and watch-folder ingestion
- Multi-satellite scheduled artifact ingestion
- ONNX workloads, runners, edge simulation, and power measurement
- Versioned API routes, bearer authentication, and OpenAPI redesign
- React, Recharts, chart export, the Money Chart, and report generation
- Importing SQLite history into PostgreSQL
- Exact GHRCE antenna coordinates or physical ground-station integration
- Milestone 2's remote GitHub Actions evidence

## Dependencies
- The locally validated Milestone 2 baseline is accepted; Milestone 3 does not depend on remote CI completion. Milestone 2 remains blocked independently until a Git remote exists.
- Docker Desktop with Compose v2 and at least 4 GB available memory.
- Public Celestrak and SatNOGS access only for the manually gated live check.
- PostgreSQL and MinIO credentials generated locally and excluded from version control.

## Design Considerations
The existing mission dashboard is a required regression surface, including loading-safe empty states, explicit stale-TLE messaging, and responsive behavior. No benchmark or placement UI appears before two honest execution targets exist.

## Operational Considerations
- PostgreSQL and MinIO versions are pinned; their data uses separate named volumes. `docker compose down` preserves both, while deletion requires an explicit documented `--volumes` destructive command.
- The application runs non-root with one Uvicorn worker. Schema migration completes before the application starts accepting traffic.
- PostgreSQL and MinIO backup/restore procedures are tested once locally. Credential rotation requires recreating service credentials and updating `.env`; secrets never enter logs or committed files.
- Health and cross-store operations use bounded timeouts and dependency-specific structured logs.

## Fundability / Demo Value
This milestone makes MissionOps the first working vertical capability of Aries and establishes trustworthy raw-data provenance for later benchmark evidence. It deliberately makes no orbital-edge performance or placement claim.