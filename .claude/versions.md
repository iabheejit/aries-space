# Version History
| Version | Date | Milestone | Changes | Files Modified |
|---------|------|-----------|---------|----------------|
| v0.1.0 | 2026-08-15 | 1 | Repo init, Mr Fox scaffold, Milestone 1 plan (READY after Vikram re-review) | CLAUDE.md, .claude/** |
| v1.0.0 | 2026-08-15 | 1 | MVP built end-to-end: pass prediction, SatNOGS ingestion, dashboard, API; 7-auditor review complete, PROCEED, all non-blocking findings fixed pre-merge | app/**, tests/**, requirements.txt, .claude/docs/** |
| v1.1.0 | 2026-08-15 | 2 | Production hardening, dashboard redesign, live-data provenance, and local container proof complete; remote CI pending | app/**, tests/**, scripts/**, Dockerfile, compose.yml, README.md, .github/** |
| v2.0.0 | 2026-08-15 | 3 | Aries storage foundation: PostgreSQL/Alembic, MinIO provenance, authenticated ingestion, MissionOps compatibility, recovery and rollback proof | services/**, tests/**, scripts/**, compose.yml, Dockerfile, README.md, .github/** |
| v2.0.1 | 2026-08-15 | 2 | M2 resolved SUPERSEDED by M3; git remote configured (private iabheejit/aries-space); merged milestone/1 + milestone/3 into main; first remote CI run caught and fixed a false-positive multi-process check in container-smoke | .github/workflows/test.yml, .claude/milestones.md, .claude/audit-trail.md |
<!-- v{major}.{minor}.{patch}: major=milestone, minor=progress, patch=fix -->
