# Aries Stage 0

Aries Stage 0 builds an orbital-edge benchmark testbed on the proven MissionOps Lite pass and satellite-health foundation. Milestone 3 stores SatNOGS provenance in PostgreSQL and checksum-verified raw payloads in MinIO while preserving the existing FastAPI API and dashboard.

The checked-in defaults use approximate GHRCE coordinates. Confirm the antenna coordinates before pilot deployment.

## Prerequisites

Install Docker Desktop with Compose v2 and allocate at least 4 GB of memory. Python 3.11 or 3.13 is required for local tests and smoke scripts.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --requirement requirements-dev.txt
cp .env.example .env && pg="$(openssl rand -hex 24)" && minio="$(openssl rand -hex 24)" && token="$(openssl rand -hex 32)" && perl -pi -e "s/replace-with-a-random-postgres-password/$pg/; s/replace-with-a-random-minio-password/$minio/; s/replace-with-a-random-64-character-token/$token/" .env
docker compose up --build --wait --wait-timeout 120
.venv/bin/python scripts/compose_smoke.py
```

Open `http://127.0.0.1:8000/`. API routes are `/api/passes`, `/api/observations`, and `/api/status`.

## Benchmark Demo

Run the complete local rehearsal against the largest stored real SatNOGS payload:

```bash
.venv/bin/python scripts/demo.py
```

The command ensures the captured real observation exists, executes the same `satnogs-payload-anomaly-proxy` workload on `ground-cpu` and `edge-sim`, persists both result objects, and prints the dashboard URL. The dashboard shows data reduction, modeled latency, energy, cost per completed run, and placement economics.

This first workload is explicitly a payload/metadata completeness proxy. It is not decoded-frame telemetry anomaly detection. `edge-sim` timing and energy are **SIMULATED**; terrestrial power is **ESTIMATED**. Neither is evidence of measured orbital or Jetson performance.

Benchmark APIs:

- `POST /api/benchmarks?dataset_id=<id>` requires the shared bearer token.
- `GET /api/benchmarks/latest?workload=satnogs-payload-anomaly-proxy` returns the latest completed atomic pair.

## Container Run

```bash
cp .env.example .env
docker compose up --build --detach --wait
curl --fail http://127.0.0.1:8000/health/ready
docker compose logs --follow app
```

Compose publishes only on `127.0.0.1` and persists PostgreSQL and MinIO in named volumes. Put a TLS-terminating, authenticated reverse proxy in front before exposing the service publicly.

Run exactly one Uvicorn worker and do not use `--reload` in production. APScheduler is in-process; extra workers or replicas would duplicate polling jobs.

## Configuration

All configuration is environment-driven; see `.env.example`. Important controls:

| Variable | Constraint | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL | Compose-managed |
| `MINIO_ENDPOINT` | MinIO host and port | `minio:9000` |
| `MINIO_ACCESS_KEY` | non-empty credential | `aries` for local development |
| `MINIO_SECRET_KEY` | at least 8 characters | local development value in `.env.example` |
| `API_BEARER_TOKEN` | random shared token for write routes | generated during setup |
| `STATION_LAT` | finite, -90 to 90 | `21.1052484` |
| `STATION_LON` | finite, -180 to 180 | `79.0034903` |
| `STATION_ELEV_M` | finite number, metres | `310` |
| `OBS_POLL_MINUTES` | at least 5 | `10` |
| `TLE_REFRESH_HOURS` | positive integer | `12` |
| `SCHEDULER_ENABLED` | true/false | `false` |
| `DOWNLINK_MBPS` | positive modeled downlink rate | `100` |
| `DOWNLINK_INR_PER_GB` | positive modeled downlink price | `500` |
| `EDGE_SIM_SLOWDOWN_FACTOR` | positive modeled latency multiplier | `4` |
| `EDGE_SIM_WATTS` | positive simulated edge power | `15` |

The GHRCE values are a public campus pin, not verified antenna coordinates. Supply the antenna GPS position before pilot deployment.

`POST /api/ingest/satnogs` requires `Authorization: Bearer <API_BEARER_TOKEN>`. Health and MissionOps read routes remain available without authentication on the localhost boundary.

## Operations

- Liveness: `GET /health/live` proves the HTTP process is running and has no database/upstream dependency.
- Readiness: `GET /health/ready` checks PostgreSQL and MinIO with bounded timeouts and returns a generic 503 when either dependency is unavailable.
- Logs: application, ingestion, scheduler, and readiness failures are emitted to stdout/stderr for collection by the container runtime.
- Graceful stop: `docker compose down` sends SIGTERM and allows 30 seconds before forced termination.

Quiesce application writes, then back up PostgreSQL and checksum-verified MinIO objects as one recovery point:

```bash
mkdir -p backups
docker compose stop app
docker compose exec -T postgres pg_dump -U aries -d aries -Fc > backups/aries.dump
.venv/bin/python scripts/storage_snapshot.py backup --destination backups/minio
docker compose up --detach --wait --wait-timeout 120 app
```

Restore both stores only after preserving the current volumes. Keep the app stopped until cross-store verification passes:

```bash
docker compose stop app
docker compose exec -T postgres pg_restore --clean --if-exists -U aries -d aries < backups/aries.dump
.venv/bin/python scripts/storage_snapshot.py restore --source backups/minio
.venv/bin/python scripts/storage_snapshot.py verify
docker compose up --detach --wait --wait-timeout 60
curl --fail http://127.0.0.1:8000/health/ready
```

## Milestone 2 Rollback

The pre-cutover SQLite volume is retained as read-only prototype evidence. Verify its backup before relying on rollback:

```bash
mkdir -p backups
docker run --rm --user 0 --entrypoint python \
	-v aries-space_missionops-data:/data:ro \
	-v "$PWD/scripts/backup_sqlite.py:/backup_sqlite.py:ro" \
	-v "$PWD/backups:/backup" \
	aries-missionops:m2-rollback /backup_sqlite.py \
	--source /data/missionops.db \
	--destination /backup/missionops-m2.sqlite3
```

The command must report `integrity_check=ok`. To temporarily restore MissionOps Lite:

```bash
docker compose down
docker compose -f ops/rollback/milestone-2.compose.yml up --detach --wait --wait-timeout 60
curl --fail http://127.0.0.1:8000/health/ready
curl --fail http://127.0.0.1:8000/api/status
```

Return to Aries without deleting either generation's volumes:

```bash
docker compose -f ops/rollback/milestone-2.compose.yml down
docker compose up --detach --wait --wait-timeout 120
```

PostgreSQL writes made after cutover are not back-ported to SQLite.

If readiness returns 503, run `docker compose logs app`, check that the volume is writable by UID `10001`, verify free disk space, and retry `docker compose restart app`. If readiness is healthy but data is stale, inspect ingestion/TLE warnings and outbound DNS/HTTPS access rather than the database.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q services tests scripts
docker compose config --quiet
```

The automated suite is offline. Live Celestrak/SatNOGS validation is a separately gated smoke run so upstream outages do not make CI flaky.

Run the bounded live validation with network access available:

```bash
SATNOGS_FIXTURE_PATH='' docker compose up --detach --force-recreate app
.venv/bin/python scripts/live_smoke.py
```

It validates current Celestrak and SatNOGS access separately from the deterministic offline suite. A timeout or upstream outage reports `BLOCKED` and never counts as a pass.

## Production Boundary

This milestone establishes storage provenance only. Redis, ONNX workloads, benchmark runners, Sentinel-2 ingestion, the Money Chart, authentication, and report generation are not included yet. It makes no orbital-edge performance or placement claim.