# Aries Mission API

All timestamps are UTC / ISO 8601. Read routes are unauthenticated on the localhost boundary. Ingestion writes require `Authorization: Bearer <API_BEARER_TOKEN>`.

## `GET /api/passes?count=N`
Next `N` (default 5, max 50) upcoming passes for the configured satellite/station, from a live Celestrak TLE (falls back to last cached TLE, flagged `tle_stale: true`, if Celestrak is unreachable; 503 if no TLE has ever been cached).

```json
{
  "satellite": {"norad_id": 68635, "name": "CANVAS"},
  "station": {"name": "GHRCE campus (approx.)", "lat": 21.1052484, "lon": 79.0034903, "elevation_m": 310.0},
  "tle_stale": false,
  "tle_fetched_at": "2026-08-15T00:36:02Z",
  "passes": [
    {"aos": "...", "los": "...", "max_elevation_deg": 51.12, "direction": "NW -> SSE"}
  ]
}
```

## `GET /api/observations?limit=25&offset=0`
Paginated, most-recent-first. `has_decoded_data` reflects whether SatNOGS provided demodulated frames; `satnogs_url` links to the full raw record (waterfall/audio/decoded frames) on network.satnogs.org.

## `GET /api/status`
PostgreSQL-derived health summary: observation counts, last successful ingestion, and configured satellite/station.

## `POST /api/ingest/satnogs`
Ingests one observation by `norad_id` and optional `observation_id`. Returns 201 when created and 200 when the checksum-verified dataset already exists. Conflicts return 409; bounded upstream/storage failures return 503.

## `GET /`
Server-rendered (Jinja2) single-page dashboard covering the same data as the three endpoints above, with explicit empty states.
