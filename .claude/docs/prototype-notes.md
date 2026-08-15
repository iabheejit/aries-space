# MissionOps Lite — Working Prototype Notes
**Date**: 2026-08-15 | **Milestone**: 1 (MVP Prototype) | **For**: DoT/TCOE India Pilot Grant, "Details of Working Prototype"

## Satellite tracked
**CANVAS** (NORAD ID 68635) — selected by querying the live SatNOGS Network API for actively-tracked satellites and picking one with frequent recent "good" observations and a registered decoder, rather than assuming a satellite in advance. Confirmed via `db.satnogs.org/api/satellites/`: status `alive`, launched 2026-04-07, decoder `canvas` registered. At time of writing it had 55+ "good" observations in the most recent 25-record page of the public feed, all carrying waterfall, audio, and decoded-frame references.

## Ground station
GHRCE (G H Raisoni College of Engineering, Nagpur) has no station currently registered in the SatNOGS network (checked all ~4,400 stations in the network — no match on name/location near Nagpur). The prototype uses GHRCE's public approximate coordinates (21.1237°N, 79.0353°E, ~310m elevation) as a placeholder. **Action needed**: confirm exact rooftop/antenna coordinates with the GHRCE team before any pilot deployment; the pass-prediction math is coordinate-driven, so this is a config change, not a code change.

## Real observations ingested
25 real, completed SatNOGS observations for CANVAS were pulled live and persisted end-to-end during this build (raw JSON + normalized fields), each with real waterfall image URLs, real audio URLs, and real decoded-frame references from SatNOGS's own CANVAS decoder — none synthetic.

## What worked
- **Pass prediction**: live TLE fetched from Celestrak (`gp.php?CATNR=68635`), computed with `skyfield` using pure two-body geometry (no ephemeris download needed). Cross-checked against an independent orbital library (`pyephem`, same TLE) — AOS/LOS/max-elevation agreed within ~2–3 minutes across two upcoming passes, inside the ±5 min tolerance in the acceptance criteria. (n2yo.com's pass predictor requires interactive location entry that isn't scriptable, so an independent second implementation was used instead of a third-party website.)
- **Ingestion**: SatNOGS `/api/observations/?norad_cat_id=68635&status=good` polled live; all 25 records stored with raw JSON intact for audit trail, deduplicated on SatNOGS observation ID.
- **Normalization**: every completed CANVAS observation in the sample had frequency, signal quality (`vetted_status`), waterfall URL, audio URL, and decoded-frame references (SatNOGS's own decoder output, not a new decoder written for this project) — full schema coverage, not the "if available" fallback case.
- **Dashboard + API**: `/api/passes`, `/api/observations`, `/api/status`, and the single-page dashboard all verified against the live, running system — status reflects real DB-derived counts (24h ingestion count, last successful ingestion timestamp), not stubs.
- **Outage handling**: TLE fetch failure falls back to the last cached TLE with a `stale` flag surfaced in the API and dashboard; SatNOGS poll failure leaves ingestion state untouched and retries next interval rather than crashing — both covered by tests using mocked network failures.
- **Scheduler**: in-process APScheduler runs an immediate ingestion poll on startup (so the dashboard isn't empty on first load) plus periodic polling (default every 10 min) and TLE refresh (default every 12h).

## What remains manual / unfinished
- GHRCE's exact station coordinates are unconfirmed (see above) — currently a documented placeholder.
- No multi-day soak test yet — the scheduler has been exercised for minutes, not the days/weeks a real pilot would run continuously; long-running stability (memory growth, SQLite file growth, scheduler drift) is unverified.
- Signal quality is surfaced as SatNOGS's own `vetted_status` (good/bad/failed/unknown) — this is community-vetted, not a first-party signal metric; acceptable per spec ("if available"), but worth noting it's not something this prototype computes itself.
- No automated CI pipeline runs the test suite yet — tests are run manually (`pytest`); fine for prototype stage, called out for DevOps follow-up.
- Explicitly out of scope per the milestone plan (unchanged): live RF/SDR reception, multi-station orchestration, anomaly detection, auth, and production hardening.

## How to reproduce
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# visit http://127.0.0.1:8000/
```
Config is env-var driven (`NORAD_ID`, `STATION_LAT`, `STATION_LON`, `STATION_ELEV_M`, `TLE_REFRESH_HOURS`, `OBS_POLL_MINUTES`, `DB_PATH`) — defaults match the CANVAS/GHRCE setup described above.
