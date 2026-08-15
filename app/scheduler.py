import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app import config
from app.db import get_session
from app.ingest import ingest_observations
from app.tle import get_tle

logger = logging.getLogger("missionops.scheduler")

_scheduler: BackgroundScheduler | None = None


def _poll_observations_job() -> None:
    with get_session() as session:
        stored = ingest_observations(session)
        if stored:
            logger.info("Ingested %d new observation(s)", stored)


def _refresh_tle_job() -> None:
    get_tle(config.NORAD_ID)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _poll_observations_job,
        "interval",
        minutes=config.OBS_POLL_MINUTES,
        next_run_time=None,  # first run scheduled explicitly below
        id="poll_observations",
    )
    scheduler.add_job(
        _refresh_tle_job,
        "interval",
        hours=config.TLE_REFRESH_HOURS,
        id="refresh_tle",
    )
    scheduler.start()

    # Run once immediately on startup so the dashboard has data without
    # waiting a full poll interval.
    scheduler.modify_job("poll_observations", next_run_time=datetime.now())

    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
