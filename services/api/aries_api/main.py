import logging
import hmac
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.api.aries_api import config
from services.api.aries_api.db import check_database, get_session
from services.api.aries_api.ingest import (
    IngestConflictError,
    IngestUnavailableError,
    fetch_observation,
    ingest_satnogs_observation,
)
from services.api.aries_api.models import Observation
from services.api.aries_api.predict import compute_passes
from services.api.aries_api.scheduler import start_scheduler, stop_scheduler
from services.api.aries_api.status import compute_status
from services.api.aries_api.storage import ObjectStore
from services.api.aries_api.tle import TLEUnavailableError, get_tle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aries.health")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
readiness_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="readiness")
bearer_scheme = HTTPBearer(auto_error=False)


def get_store() -> ObjectStore:
    return ObjectStore()


def _bounded_check(check) -> None:
    future = readiness_executor.submit(check)
    try:
        future.result(timeout=config.READINESS_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.cancel()
        raise TimeoutError("dependency readiness check timed out")


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not hmac.compare_digest(credentials.credentials, config.API_BEARER_TOKEN)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    store = get_store()
    store.ensure_buckets()
    if config.SCHEDULER_ENABLED:
        start_scheduler()
    try:
        yield
    finally:
        if config.SCHEDULER_ENABLED:
            stop_scheduler()


app = FastAPI(title="MissionOps Lite", lifespan=lifespan)


@app.get("/health/live")
def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready(store: ObjectStore = Depends(get_store)):
    try:
        _bounded_check(check_database)
    except Exception:
        logger.error("readiness_failed dependency=postgresql")
        raise HTTPException(status_code=503, detail="Service is not ready")
    try:
        _bounded_check(store.check)
    except Exception:
        logger.error("readiness_failed dependency=minio")
        raise HTTPException(status_code=503, detail="Service is not ready")
    return {"status": "ready"}


def _passes_payload(count: int) -> dict:
    try:
        tle = get_tle(config.NORAD_ID)
    except TLEUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    passes = compute_passes(tle, config.STATION_LAT, config.STATION_LON, config.STATION_ELEV_M, count)
    return {
        "tle_stale": tle.stale,
        "tle_fetched_at": tle.fetched_at.isoformat(),
        "passes": [
            {"aos": item["aos"].isoformat(), "los": item["los"].isoformat(), "max_elevation_deg": item["max_elevation_deg"], "direction": item["direction"]}
            for item in passes
        ],
    }


@app.get("/api/passes")
def api_passes(count: int = Query(default=5, ge=1, le=50)):
    return {
        "satellite": {"norad_id": config.NORAD_ID, "name": config.SATELLITE_NAME},
        "station": {"name": config.STATION_NAME, "lat": config.STATION_LAT, "lon": config.STATION_LON, "elevation_m": config.STATION_ELEV_M},
        **_passes_payload(count),
    }


@app.get("/api/observations")
def api_observations(limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    rows = session.scalars(select(Observation).order_by(Observation.timestamp.desc()).offset(offset).limit(limit)).all()
    total = session.scalar(select(func.count()).select_from(Observation)) or 0
    return {"total": total, "limit": limit, "offset": offset, "observations": [
        {"satnogs_observation_id": row.satnogs_observation_id, "satellite_id": row.satellite_id, "station_id": row.station_id, "timestamp": row.timestamp.isoformat(), "frequency": row.frequency, "signal_quality": row.signal_quality, "waterfall_url": row.waterfall_url, "audio_url": row.audio_url, "has_decoded_data": row.decoded_data is not None, "satnogs_url": f"https://network.satnogs.org/observations/{row.satnogs_observation_id}/"}
        for row in rows
    ]}


@app.get("/api/status")
def api_status(session: Session = Depends(get_session)):
    return compute_status(session)


@app.post("/api/ingest/satnogs")
def api_ingest_satnogs(
    response: Response,
    norad_id: int = Query(..., gt=0),
    limit: int = Query(1, ge=1, le=1),
    observation_id: int | None = Query(None, gt=0),
    session: Session = Depends(get_session),
    store: ObjectStore = Depends(get_store),
    _: None = Depends(require_admin),
):
    try:
        raw = fetch_observation(norad_id, limit, observation_id)
        result = ingest_satnogs_observation(session, store, raw, norad_id)
    except IngestConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IngestUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    response.status_code = 201 if result.created else 200
    return {"dataset_id": result.dataset_id, "external_id": result.external_id, "object_key": result.object_key, "size_bytes": result.size_bytes, "sha256": result.sha256}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    try:
        status = compute_status(session)
        recent = session.scalars(
            select(Observation).order_by(Observation.timestamp.desc()).limit(10)
        ).all()
        database_error = None
    except SQLAlchemyError:
        logger.error("dashboard_degraded dependency=postgresql")
        status = {
            "observations_ingested_last_24h": "Unavailable",
            "observations_total": "Unavailable",
            "last_successful_ingestion": None,
        }
        recent = []
        database_error = "Mission storage is temporarily unavailable. Retry shortly."
    try:
        passes_payload = _passes_payload(5)
        passes_error = None
    except HTTPException as exc:
        passes_payload = {"passes": [], "tle_stale": False}
        passes_error = exc.detail
    return templates.TemplateResponse(request, "dashboard.html", {
        "satellite_name": config.SATELLITE_NAME, "norad_id": config.NORAD_ID, "station_name": config.STATION_NAME, "station_lat": config.STATION_LAT, "station_lon": config.STATION_LON, "station_elev_m": config.STATION_ELEV_M,
        "status": status, "database_error": database_error, "passes": passes_payload["passes"], "passes_error": passes_error, "tle_stale": passes_payload["tle_stale"],
        "observations": [{"timestamp": row.timestamp, "satellite_id": row.satellite_id, "signal_quality": row.signal_quality, "satnogs_url": f"https://network.satnogs.org/observations/{row.satnogs_observation_id}/"} for row in recent],
    })