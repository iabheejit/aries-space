import json
import logging
import hmac
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.api.aries_api import config
from services.api.aries_api.benchmarks import (
    DEFAULT_WORKLOAD_SLUG,
    WORKLOAD_REGISTRY,
    BenchmarkNotFoundError,
    BenchmarkUnavailableError,
    DatasetIneligibleError,
    DatasetNotFoundError,
    WorkloadNotFoundError,
    latest_completed_pair,
    run_benchmark_pair,
    serialize_pair,
)
from services.api.aries_api.dashboard_data import build_workload_matrix
from services.api.aries_api.db import check_database, get_session
from services.api.aries_api.ingest import (
    IngestConflictError,
    IngestUnavailableError,
    fetch_observation,
    ingest_satnogs_observation,
)
from services.api.aries_api.models import Observation
from services.api.aries_api.overhead import build_snapshot, ground_track_for
from services.api.aries_api.predict import compute_passes
from services.api.aries_api.scheduler import start_scheduler, stop_scheduler
from services.api.aries_api.sentinel2_ingest import (
    AOI_GHRCE_AGRICULTURAL,
    fetch_sentinel2_crop,
    ingest_sentinel2_crop,
)
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


app = FastAPI(title="Aries Stage 0 Testbed", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


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


def _infra_health(store: ObjectStore) -> dict:
    """Real backend infrastructure health.

    This is the Aries application stack's own health (Postgres, MinIO) -- not
    spacecraft bus telemetry. Aries has no flight hardware, so there is no
    real "processor load" or "thermal state" to report; reporting the
    infrastructure that actually exists is the honest analogue.
    """
    postgres_ok = True
    try:
        _bounded_check(check_database)
    except Exception:
        postgres_ok = False
    minio_ok = True
    try:
        _bounded_check(store.check)
    except Exception:
        minio_ok = False
    return {"postgres_ok": postgres_ok, "minio_ok": minio_ok}


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


@app.get("/api/overhead")
def api_overhead(offset_minutes: float = Query(default=0.0, ge=-720, le=720)):
    moment = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    try:
        return build_snapshot(moment)
    except TLEUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/overhead/track")
def api_overhead_track(
    norad_id: int = Query(..., gt=0),
    minutes: int = Query(default=config.GROUND_TRACK_MINUTES, ge=1, le=720),
):
    try:
        track = ground_track_for(norad_id, minutes=minutes)
    except TLEUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not track:
        raise HTTPException(status_code=404, detail=f"No TLE found for NORAD {norad_id}")
    return {"norad_id": norad_id, "minutes": minutes, "track": track}


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


@app.post("/api/ingest/sentinel2")
def api_ingest_sentinel2(
    response: Response,
    aoi_id: int = Query(AOI_GHRCE_AGRICULTURAL, gt=0),
    session: Session = Depends(get_session),
    store: ObjectStore = Depends(get_store),
    _: None = Depends(require_admin),
):
    try:
        payload = fetch_sentinel2_crop(aoi_id)
        result = ingest_sentinel2_crop(session, store, payload, aoi_id)
    except IngestUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown aoi_id {aoi_id}") from exc
    response.status_code = 201 if result.created else 200
    return {"dataset_id": result.dataset_id, "external_id": result.external_id, "object_key": result.object_key, "size_bytes": result.size_bytes, "sha256": result.sha256}


@app.post("/api/benchmarks", status_code=201)
def api_run_benchmark(
    dataset_id: int = Query(..., gt=0),
    workload: str = Query(DEFAULT_WORKLOAD_SLUG),
    session: Session = Depends(get_session),
    store: ObjectStore = Depends(get_store),
    _: None = Depends(require_admin),
):
    try:
        pair = run_benchmark_pair(session, store, dataset_id, workload_slug=workload)
        return serialize_pair(session, pair)
    except WorkloadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatasetIneligibleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BenchmarkUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/benchmarks/latest")
def api_latest_benchmark(
    workload: str = Query(DEFAULT_WORKLOAD_SLUG),
    session: Session = Depends(get_session),
):
    try:
        return serialize_pair(session, latest_completed_pair(session, workload))
    except BenchmarkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BenchmarkUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/benchmarks/matrix")
def api_benchmark_matrix(session: Session = Depends(get_session)):
    """Real latest-completed-pair economics for every registered workload.

    Workloads with no completed pair yet are omitted, not padded.
    """
    matrix = build_workload_matrix(
        session,
        list(WORKLOAD_REGISTRY.keys()),
        latest_completed_pair,
        serialize_pair,
        BenchmarkNotFoundError,
        BenchmarkUnavailableError,
    )
    return {"workloads": matrix, "total_registered": len(WORKLOAD_REGISTRY)}


def _dashboard_context(session: Session) -> dict:
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
        benchmark = serialize_pair(session, latest_completed_pair(session))
        benchmark_error = None
    except BenchmarkNotFoundError:
        benchmark = None
        benchmark_error = "No benchmark pair has been run yet."
    except (BenchmarkUnavailableError, SQLAlchemyError):
        benchmark = None
        benchmark_error = "Benchmark comparison is temporarily unavailable."
    try:
        passes_payload = _passes_payload(5)
        passes_error = None
    except HTTPException as exc:
        passes_payload = {"passes": [], "tle_stale": False}
        passes_error = exc.detail
    return {
        "satellite_name": config.SATELLITE_NAME, "norad_id": config.NORAD_ID, "station_name": config.STATION_NAME, "station_lat": config.STATION_LAT, "station_lon": config.STATION_LON, "station_elev_m": config.STATION_ELEV_M,
        "status": status, "database_error": database_error, "benchmark": benchmark, "benchmark_error": benchmark_error, "passes": passes_payload["passes"], "passes_error": passes_error, "tle_stale": passes_payload["tle_stale"],
        "observations": [{"timestamp": row.timestamp, "satellite_id": row.satellite_id, "signal_quality": row.signal_quality, "satnogs_url": f"https://network.satnogs.org/observations/{row.satnogs_observation_id}/"} for row in recent],
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "dashboard.html", _dashboard_context(session))

def _workload_matrix(session: Session) -> list[dict]:
    return build_workload_matrix(
        session,
        list(WORKLOAD_REGISTRY.keys()),
        latest_completed_pair,
        serialize_pair,
        BenchmarkNotFoundError,
        BenchmarkUnavailableError,
    )


@app.get("/dashboard/orbital-iq", response_class=HTMLResponse)
def dashboard_orbital_iq(
    request: Request,
    session: Session = Depends(get_session),
    store: ObjectStore = Depends(get_store),
):
    """Orbital IQ 'Mission Control' -- overview page.

    Mission health, orbital positions, and the headline edge-economics
    comparison, all real. Deeper per-workload views live on their own pages:
    /dashboard/events (run log/detail/economics) and /dashboard/commercial
    (workload coverage + aggregate economics). Only the map's SAR/AIS
    sensor-fusion layer has no real analogue and stays badged CONCEPT.
    """
    context = _dashboard_context(session)
    context["workload_matrix"] = _workload_matrix(session)
    context["infra_health"] = _infra_health(store)
    return templates.TemplateResponse(
        request, "dashboard_orbital_iq.html", context
    )


@app.get("/dashboard/events", response_class=HTMLResponse)
def dashboard_events(request: Request, session: Session = Depends(get_session)):
    """Orbital IQ 'Events' page -- real benchmark run log, detail, economics.

    Every registered workload's latest completed pair, real; nothing here is
    a fabricated detection event.
    """
    context = {
        "satellite_name": config.SATELLITE_NAME, "norad_id": config.NORAD_ID,
        "station_name": config.STATION_NAME, "station_lat": config.STATION_LAT,
        "station_lon": config.STATION_LON, "station_elev_m": config.STATION_ELEV_M,
    }
    matrix = _workload_matrix(session)
    context["workload_matrix"] = matrix
    context["workload_matrix_json"] = json.dumps(matrix).replace("</", "<\\/")
    return templates.TemplateResponse(request, "dashboard_events.html", context)


@app.get("/dashboard/commercial", response_class=HTMLResponse)
def dashboard_commercial(request: Request, session: Session = Depends(get_session)):
    """Orbital IQ 'Commercial' page -- real workload coverage + aggregate
    economics. No customer or revenue data exists, so neither is shown here;
    see the roadmap's Stage 9 note for why."""
    context = {
        "satellite_name": config.SATELLITE_NAME, "norad_id": config.NORAD_ID,
        "station_name": config.STATION_NAME, "station_lat": config.STATION_LAT,
        "station_lon": config.STATION_LON, "station_elev_m": config.STATION_ELEV_M,
    }
    context["workload_matrix"] = _workload_matrix(session)
    return templates.TemplateResponse(request, "dashboard_commercial.html", context)


@app.get("/dashboard/concept", response_class=HTMLResponse)
def dashboard_concept(request: Request, session: Session = Depends(get_session)):
    """Vision-stage layout replicating the founder's Orbital IQ mockup structure.

    Real Aries data fills every panel it can (mission health, edge economics,
    passes, observations). Panels with no real backing data (fused sensor map,
    event queue, customer/revenue) are explicitly labelled SIMULATED CONCEPT
    DATA -- not measured, not a real customer, not a real detection.
    """
    return templates.TemplateResponse(request, "dashboard_concept.html", _dashboard_context(session))


@app.get("/dashboard/map", response_class=HTMLResponse)
def dashboard_map(request: Request):
    """Dedicated, full-page orbital map.

    Deliberately has no database dependency -- every satellite position it
    draws comes from live Celestrak TLEs propagated with real SGP4 (Skyfield),
    not from Postgres, so this page keeps working even if the database is
    down. SAR/AIS layers have no real feed and refuse to switch on.
    """
    return templates.TemplateResponse(request, "dashboard_map.html", {
        "satellite_name": config.SATELLITE_NAME, "norad_id": config.NORAD_ID,
        "station_name": config.STATION_NAME, "station_lat": config.STATION_LAT,
        "station_lon": config.STATION_LON, "station_elev_m": config.STATION_ELEV_M,
    })