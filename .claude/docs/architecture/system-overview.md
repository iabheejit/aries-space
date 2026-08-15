# System Overview — Aries Stage 0

Single-process FastAPI app with PostgreSQL metadata, MinIO objects, Alembic migrations, bearer-authenticated writes, and in-process APScheduler. MissionOps pass and health views are the first Aries capability.

## Modules (`services/api/aries_api/`)
- `config.py` — env-var driven settings (NORAD ID, station coords, poll/refresh intervals, DB path)
- `tle.py` — Celestrak TLE fetch with in-memory cache + stale-on-outage fallback
- `predict.py` — skyfield pass computation (rise/culminate/set events → AOS/LOS/max-elevation/direction)
- `ingest.py` — SatNOGS observation polling, dedup on `satnogs_observation_id`, per-record error isolation
- `normalize.py` — raw SatNOGS JSON → structured `Observation` fields, tolerant of missing optional fields
- `models.py` / `db.py` — SQLAlchemy models and bounded PostgreSQL access
- `storage.py` — MinIO buckets and byte retrieval for checksum verification
- `status.py` — DB-derived health summary (not wall-clock timestamps)
- `scheduler.py` — APScheduler background jobs (poll observations, refresh TLE), immediate first-run on startup
- `main.py` — FastAPI routes + Jinja2 dashboard

## Data flow
Celestrak feeds pass prediction. SatNOGS observations are canonicalized, stored under deterministic MinIO keys, byte-hashed, and linked to PostgreSQL dataset/observation rows. PostgreSQL advisory locks serialize identical ingests; failed database commits compensate only objects owned by that attempt.

## Known scale limits (prototype, not production)
- Single in-process scheduler instance — fine for one operator/one satellite; would need an external scheduler or lock if run multi-instance.
- `Pass` table exists in the schema but predictions are computed on-demand, not persisted — acceptable since no acceptance criterion required historical pass storage.
- One application worker owns APScheduler; horizontal replicas require external scheduling or leader election.
- Bearer auth protects ingestion writes; read routes remain localhost-facing and unauthenticated.
- Redis, ONNX workloads, runners, metrics, React, and reports remain later Stage 0 milestones.
