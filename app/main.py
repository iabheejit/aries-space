from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from app import config
from app.db import get_session, init_db
from app.models import Observation
from app.predict import compute_passes
from app.scheduler import start_scheduler, stop_scheduler
from app.status import compute_status
from app.tle import TLEUnavailableError, get_tle

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="MissionOps Lite", lifespan=lifespan)


def _satnogs_url(observation_id: int) -> str:
    return f"https://network.satnogs.org/observations/{observation_id}/"


def _passes_payload(count: int) -> dict:
    try:
        tle = get_tle(config.NORAD_ID)
    except TLEUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    passes = compute_passes(
        tle,
        lat=config.STATION_LAT,
        lon=config.STATION_LON,
        elev_m=config.STATION_ELEV_M,
        count=count,
    )
    return {
        "tle_stale": tle.stale,
        "tle_fetched_at": tle.fetched_at.isoformat(),
        "passes": [
            {
                "aos": p["aos"].isoformat(),
                "los": p["los"].isoformat(),
                "max_elevation_deg": p["max_elevation_deg"],
                "direction": p["direction"],
            }
            for p in passes
        ],
    }


@app.get("/api/passes")
def api_passes(count: int = Query(default=5, ge=1, le=50)):
    payload = _passes_payload(count)
    return {
        "satellite": {"norad_id": config.NORAD_ID, "name": config.SATELLITE_NAME},
        "station": {
            "name": config.STATION_NAME,
            "lat": config.STATION_LAT,
            "lon": config.STATION_LON,
            "elevation_m": config.STATION_ELEV_M,
        },
        **payload,
    }


@app.get("/api/observations")
def api_observations(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    with get_session() as session:
        rows = session.exec(
            select(Observation)
            .order_by(Observation.timestamp.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        total = len(session.exec(select(Observation)).all())

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "observations": [
            {
                "satnogs_observation_id": o.satnogs_observation_id,
                "satellite_id": o.satellite_id,
                "station_id": o.station_id,
                "timestamp": o.timestamp.isoformat(),
                "frequency": o.frequency,
                "signal_quality": o.signal_quality,
                "waterfall_url": o.waterfall_url,
                "audio_url": o.audio_url,
                "has_decoded_data": o.decoded_data is not None,
                "satnogs_url": _satnogs_url(o.satnogs_observation_id),
            }
            for o in rows
        ],
    }


@app.get("/api/status")
def api_status():
    with get_session() as session:
        return compute_status(session)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with get_session() as session:
        status = compute_status(session)
        recent = session.exec(
            select(Observation).order_by(Observation.timestamp.desc()).limit(10)
        ).all()

    try:
        passes_payload = _passes_payload(count=5)
        passes_error = None
    except HTTPException as exc:
        passes_payload = {"passes": [], "tle_stale": False, "tle_fetched_at": None}
        passes_error = exc.detail

    observations = [
        {
            "timestamp": o.timestamp,
            "satellite_id": o.satellite_id,
            "signal_quality": o.signal_quality,
            "satnogs_url": _satnogs_url(o.satnogs_observation_id),
        }
        for o in recent
    ]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "satellite_name": config.SATELLITE_NAME,
            "norad_id": config.NORAD_ID,
            "station_name": config.STATION_NAME,
            "station_lat": config.STATION_LAT,
            "station_lon": config.STATION_LON,
            "station_elev_m": config.STATION_ELEV_M,
            "status": status,
            "passes": passes_payload["passes"],
            "passes_error": passes_error,
            "tle_stale": passes_payload["tle_stale"],
            "observations": observations,
        },
    )
