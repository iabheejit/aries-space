# Milestone 2: Production Readiness and End-to-End Validation
**Created**: 2026-08-15 | **Project**: MissionOps Lite (aries-space)

## Objective
Turn the completed single-operator MVP into a reproducible, observable, single-instance production service and prove the complete live data path from Celestrak and SatNOGS through SQLite to the API and dashboard.

## Production Boundary
This milestone targets one application process and one persistent SQLite volume, deployed behind a TLS-terminating reverse proxy or on a private network. Public internet authentication, horizontal scaling, multi-station orchestration, and managed-database migration remain outside this milestone.

## Acceptance Criteria
1. `GET /health/live` returns HTTP 200 without touching SQLite, Celestrak, or SatNOGS. `GET /health/ready` executes `SELECT 1`, returns 200 on success, and returns a generic 503 on failure. Automated tests force DB and upstream failures to prove liveness independence and cover both readiness outcomes.
2. Runtime configuration accepts only finite latitude `[-90, 90]`, finite longitude `[-180, 180]`, finite elevation, positive TLE refresh hours, and SatNOGS polling of at least five minutes. Invalid values raise a named configuration error during import/startup with the variable name in the message. Database initialization creates a missing writable parent and raises clearly for a deterministic file-as-parent case. Defaults remain CANVAS and the documented approximate, not confirmed, GHRCE coordinates.
3. Tests query and assert `PRAGMA foreign_keys = 1`, `PRAGMA journal_mode = wal`, and the configured non-zero `PRAGMA busy_timeout`. Scheduler tests assert `max_instances=1`, `coalesce=True`, captured exception logging, and repeated shutdown without error.
4. A non-root Docker image and Compose definition start exactly one Uvicorn worker, persist `/data/missionops.db`, expose a health check, and bind to localhost by default. A mandatory CI container smoke job asserts a non-root UID, one server process, localhost-only published binding, healthy status, and database persistence across container recreation. `docker compose config` plus the same image build/start checks run locally when Docker is available; local Docker absence is recorded but cannot replace the mandatory CI proof.
5. `.env.example` and `README.md` document local and container startup, configuration, reverse-proxy/TLS assumptions, backup/restore, health checks, and the single-worker constraint. Production dependencies are separated from test-only dependencies.
6. CI runs `python -m pytest -q` on Python 3.11 and 3.13, then builds and runs the container smoke checks from AC4 without calling live application upstreams. Locally, `python -m pytest -q`, Pylance workspace diagnostics, `python -m compileall -q app tests`, and a single-worker Uvicorn HTTP smoke test all pass.
7. A manually gated live smoke command starts a single-worker server with a unique temporary `DB_PATH`; the startup scheduler polls SatNOGS immediately, and the command polls readiness/status for at most 90 seconds. It verifies: `/health/live` and `/health/ready` return 200; `/api/passes?count=1` returns one or more passes; `/api/status` reports one or more observations; SQLite contains a recorded SatNOGS observation ID, non-empty `raw_json`, and populated `timestamp`, `satellite_id`, `station_id`, `frequency`, and `signal_quality`; `/` returns 200 with `Mission Health`, `Upcoming Passes`, and `Recent Observations`. Record UTC timestamp and evidence in the session log, then stop the process and remove the temporary DB. Timeout or upstream outage produces `BLOCKED` and is retryable, never a pass. The pass location remains the approximate, unconfirmed GHRCE coordinates.

## Execution Sequence
1. Runtime contracts: configuration validation, SQLite durability settings, health endpoints, scheduler controls, and focused tests.
2. Packaging and operations: dependency split, Docker/Compose, environment template, CI, and runbook.
3. Verification: full tests and diagnostics, container checks where available, then live end-to-end smoke test with an isolated database.

## Security and Operational Constraints
- No secrets are required by the upstream public APIs. Any future proxy credentials stay outside the repository.
- Compose binds to `127.0.0.1`; public exposure requires an operator-managed TLS/authenticated reverse proxy.
- Exactly one Uvicorn worker is required while APScheduler remains in process, preventing duplicate polling jobs.
- The SQLite file and its WAL/SHM sidecars live on a persistent volume and must be backed up using SQLite's online backup command.
- Health responses do not expose exception details or upstream payloads.

## Dependencies
- Docker Engine with Compose v2 for local container proof; GitHub Actions for CI execution.
- Outbound DNS and HTTPS access to Celestrak and SatNOGS for the manually gated live validation.
- A filesystem/volume that permits SQLite files plus WAL/SHM sidecars and is writable by the container's non-root UID.
- Dependency compatibility with Python 3.11 and 3.13.

## Risks
- Celestrak or SatNOGS availability/schema changes can block live validation; retain existing cached-TLE and ingestion retry behavior.
- Uvicorn reload or multiple workers would create duplicate in-process schedulers; production commands must use one worker with reload disabled.
- SQLite remains a single-instance storage choice; network filesystems without reliable locking are unsupported.
- GHRCE coordinates are approximate until confirmed by the station team, so pilot-location accuracy remains an external dependency.

## Files Expected
- `app/config.py`, `app/db.py`, `app/main.py`, `app/scheduler.py`
- `tests/test_api.py`, plus focused configuration/database/scheduler tests as needed
- `requirements.txt`, `requirements-dev.txt`
- `Dockerfile`, `compose.yml`, `.dockerignore`, `.env.example`
- `.github/workflows/test.yml`, `README.md`
- `.claude/session-log.md`, `.claude/milestones.md`, `.claude/versions.md`

## Out of Scope
- Kubernetes, autoscaling, or multiple application workers
- Built-in user accounts, authorization, or TLS termination
- PostgreSQL migration and schema-migration tooling
- RF hardware control, new decoders, anomaly detection, or multi-station routing

Reproducible deployment and captured real-data evidence strengthen the prototype's TRL 6 pilot-readiness claim without expanding its product scope.