import logging
from datetime import datetime

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.background import BackgroundScheduler

from services.api.aries_api import config
from services.api.aries_api.db import SessionLocal
from services.api.aries_api.ingest import fetch_observation, ingest_satnogs_observation
from services.api.aries_api.storage import ObjectStore
from services.api.aries_api.tle import get_tle

logger = logging.getLogger("aries.scheduler")
_scheduler: BackgroundScheduler | None = None


def _poll_observations_job() -> None:
    raw = fetch_observation(config.NORAD_ID)
    with SessionLocal() as session:
        result = ingest_satnogs_observation(session, ObjectStore(), raw, config.NORAD_ID)
    logger.info("SatNOGS poll completed: dataset_id=%d created=%s", result.dataset_id, result.created)


def _refresh_tle_job() -> None:
    get_tle(config.NORAD_ID)


def _log_job_error(event: JobExecutionEvent) -> None:
    if event.exception is not None:
        logger.error(
            "Scheduler job %s failed",
            event.job_id,
            exc_info=(type(event.exception), event.exception, event.exception.__traceback__),
        )


def _build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1})
    scheduler.add_listener(_log_job_error, EVENT_JOB_ERROR)
    scheduler.add_job(
        _poll_observations_job,
        "interval",
        minutes=config.OBS_POLL_MINUTES,
        id="poll_observations",
    )
    scheduler.add_job(_refresh_tle_job, "interval", hours=config.TLE_REFRESH_HOURS, id="refresh_tle")
    return scheduler


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        candidate = _build_scheduler()
        try:
            candidate.start()
            candidate.modify_job("poll_observations", next_run_time=datetime.now())
        except Exception:
            if candidate.running:
                candidate.shutdown(wait=False)
            raise
        _scheduler = candidate
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=True)
        _scheduler = None