# Aries (aries-space)

**Engineering OS**: Mr Fox CTO is active on this project.

At every session start:
1. Read `.claude/milestones.md` and last 3 entries in `.claude/session-log.md`
2. Find and read only the most recent `### CTO Consolidated` section in `.claude/audit-trail.md`
3. Brief: current milestone, status, blockers, what to run at

Eight specialists in `.claude/agents/`. Spawn in parallel at milestone gates.
Slash commands: /mr-fox-boot /mr-fox-status /mr-fox-plan /mr-fox-plan-review /mr-fox-audit /mr-fox-milestone-complete /mr-fox-log

## Project Context

**Aries** is one project, not two. "MissionOps Lite" is its original name and remains the name of its first capability (satellite pass prediction + SatNOGS telemetry dashboard) — it was never a separate codebase, and there is nothing to merge. Built for a DoT/TCOE India Pilot Grant application (TRL 4→6 validation), it has since grown into a broader end goal: Aries as the neutral control plane for compute placement across satellite and terrestrial infrastructure ("given a workload, recommend and eventually execute the best placement: ground, edge/orbit, or hybrid"). See `.claude/plans/` for the full milestone history and `biz/orbital-compute-access-plan.md` for ground/orbital provider access strategy.

Real data only, no synthetic/mock data: Celestrak TLE + SatNOGS Network API for satellite telemetry, AWS Open Data (Sentinel-2) for imagery workloads. Target ground station: GHRCE (SatNOGS network participant, approximate coordinates pending confirmation).

**Current stack**: Python, FastAPI, skyfield, httpx, PostgreSQL (via SQLAlchemy + Alembic migrations), MinIO (raw object/provenance storage), Jinja2 dashboard, APScheduler. Runs via Docker Compose (`compose.yml`); package lives at `services/api/aries_api/`.

**Milestone status** (see `.claude/milestones.md` for current detail): M1 MVP Prototype (SQLite-era) COMPLETED; M2 Production Readiness SUPERSEDED by M3; M3 Aries Storage Foundation (Postgres/MinIO/Alembic, MissionOps preserved) COMPLETED; M4 Benchmark Kernel and Money Chart IN_PROGRESS.

Full roadmap and vision: see the "Aries end-goal roadmap" project memory, `.claude/plans/`, and `README.md`.
