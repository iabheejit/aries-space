# MissionOps Lite

**Engineering OS**: Mr Fox CTO is active on this project.

At every session start:
1. Read `.claude/milestones.md` and last 3 entries in `.claude/session-log.md`
2. Find and read only the most recent `### CTO Consolidated` section in `.claude/audit-trail.md`
3. Brief: current milestone, status, blockers, what to run at

Eight specialists in `.claude/agents/`. Spawn in parallel at milestone gates.
Slash commands: /mr-fox-boot /mr-fox-status /mr-fox-plan /mr-fox-plan-review /mr-fox-audit /mr-fox-milestone-complete /mr-fox-log

## Project Context

Satellite mission-operations dashboard prototype built for a DoT/TCOE India Pilot Grant application (TRL 4→6 validation). Must use real satellite data (Celestrak TLE + SatNOGS Network API), no synthetic/mock data. Deployable in ~1 week without physical RF hardware. Target pilot: GHRCE ground station (SatNOGS network participant).

Stack: Python, FastAPI, skyfield, httpx, SQLite, Jinja2/minimal JS, APScheduler.

Full spec: see `.claude/plans/milestone-1-mvp-prototype.md`.
