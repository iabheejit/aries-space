# Changelog
<!-- Auto-generated at milestone completion. Grouped by version. -->
<!-- Format: ## [v{X}] — {date} — Milestone {N}: {name} -->
<!-- Categories: Added / Changed / Fixed / Removed -->

## [v1.0.0] — 2026-08-15 — Milestone 1: MVP Prototype

### Added
- Live pass prediction (`GET /api/passes`) for CANVAS (NORAD 68635) over GHRCE using skyfield + live Celestrak TLEs, with stale-cache fallback on outage
- SatNOGS observation ingestion (`app/ingest.py`) with raw JSON audit-trail storage and dedup
- Normalization layer (`app/normalize.py`) mapping raw SatNOGS records into a structured schema
- SQLite storage via SQLModel (`Pass`, `Observation` tables)
- `GET /api/observations` (paginated) and `GET /api/status` (DB-derived health summary)
- Server-rendered dashboard (`GET /`) with mission health, upcoming passes, and recent observations, including explicit empty states
- APScheduler background polling (observations + TLE refresh), immediate first run on startup
- 14 automated tests covering prediction, normalization, ingestion (including outage handling), and API/dashboard shape
- `.claude/docs/prototype-notes.md` — grant-application writeup

### Changed (post-audit fixes)
- Per-record error isolation in ingestion (one malformed SatNOGS record no longer aborts the batch)
- `logging.basicConfig` added so ingestion activity is visible under uvicorn
- Pinned all dependency versions in `requirements.txt`
- `/api/observations` total count now uses `func.count()` instead of loading the full table
- `/api/status` ingestion-error message sanitized for anonymous viewers (full detail stays in server logs)
- Dashboard: added viewport meta tag

## [v1.1.0] — 2026-08-15 — Milestone 2: Production Readiness (blocked)

### Added
- Independent liveness and SQLite-backed readiness endpoints
- Fail-fast environment validation for coordinates, polling intervals, SQLite timeout, and scheduler control
- Non-root single-worker Docker image, localhost-only Compose service, persistent SQLite volume, and health check
- Python 3.11/3.13 CI matrix with mandatory container runtime, persistence, and backup/restore smoke checks
- Bounded canonical live-smoke runner and complete operator runbook

### Changed
- SQLite now uses WAL, foreign keys, busy timeout, restrictive file permissions, and prepared parent directories
- Scheduler jobs coalesce, cannot overlap, log failures, clean up partial startup, and wait for active jobs on shutdown
- Ingestion treats malformed JSON/schema responses as retryable failures and isolates malformed records
- Dashboard improves narrow-screen table behavior, contrast, link labels, and empty-state wording
- Test suite expanded from 14 to 38 tests with direct SQL and lifecycle contract checks

### Validation
- Local container proof passed: non-root UID 10001, one Uvicorn process, localhost-only binding, healthy readiness, volume persistence, and backup/restore integrity
- Full suite passed on Python 3.11 and 3.13; the production container passed live SatNOGS ingestion, Celestrak pass prediction, SQLite persistence, and dashboard rendering
- Dashboard refreshed as a responsive mission-control surface and checked at desktop/mobile viewports with no page-level overflow
- Remote GitHub Actions execution remains pending because no Git remote is configured

## [v2.0.0] — 2026-08-15 — Milestone 3: Aries Storage Foundation

### Added
- PostgreSQL 15 metadata storage with SQLAlchemy 2.x and reversible Alembic migration
- MinIO `raw`, `processed`, and `results` buckets with deterministic object keys and SHA-256 provenance
- Bearer-authenticated SatNOGS ingestion write endpoint with fixture and manually gated live modes
- Real PostgreSQL/MinIO concurrency and compensation tests, paired storage snapshot/restore, and executable SQLite rollback

### Changed
- MissionOps moved from `app/` to the single `services/api/aries_api` runtime while preserving dashboard and read API contracts
- GHRCE default moved to the public campus pin and remains explicitly labeled approximate
- Readiness now checks PostgreSQL and MinIO under a hard deadline; dashboard renders a sanitized degraded-storage state
- CI now gates Alembic round trips, real cross-store integration, non-root runtime, checksums, idempotency, and persistence
- Runtime images are digest-pinned and Compose refuses missing storage/API secrets

### Fixed
- Serialized same-observation ingestion with PostgreSQL advisory locks to prevent winner-object deletion races
- Pre-existing MinIO objects are downloaded and byte-hashed instead of trusting metadata
- MinIO lookup/read failures return controlled 503 responses; upload ambiguity and cleanup states have explicit tests

### Validation
- 49 tests passed in the final rebuilt gate, including isolated migration and real PostgreSQL/MinIO tests
- Live SatNOGS observation `14790343` and fixture `14790266` passed idempotency and checksum verification
- Paired PostgreSQL/MinIO recovery restored a deliberately deleted object; Milestone 2 rollback returned 25 SQLite observations and Aries recovered intact
<!-- End of changelog -->
