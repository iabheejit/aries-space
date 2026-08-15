import logging

from apscheduler.events import EVENT_JOB_ERROR

from services.api.aries_api import scheduler


def test_scheduler_jobs_do_not_overlap_and_coalesce():
    instance = scheduler._build_scheduler()
    assert any(
        callback is scheduler._log_job_error and event_mask & EVENT_JOB_ERROR
        for callback, event_mask in instance._listeners
    )
    instance.start(paused=True)

    try:
        jobs = instance.get_jobs()

        assert {job.id for job in jobs} == {"poll_observations", "refresh_tle"}
        assert all(job.max_instances == 1 for job in jobs)
        assert all(job.coalesce is True for job in jobs)
    finally:
        instance.shutdown()


def test_scheduler_logs_job_failures(caplog):
    failure = RuntimeError("upstream unavailable")
    event = type(
        "FailedJobEvent",
        (),
        {"exception": failure, "job_id": "poll_observations"},
    )()

    with caplog.at_level(logging.ERROR, logger="aries.scheduler"):
        scheduler._log_job_error(event)

    assert "Scheduler job poll_observations failed" in caplog.text
    assert "upstream unavailable" in caplog.text


def test_scheduler_start_and_stop_are_idempotent(monkeypatch):
    monkeypatch.setattr(scheduler, "_poll_observations_job", lambda: None)
    first = scheduler.start_scheduler()
    second = scheduler.start_scheduler()

    assert first is second

    scheduler.stop_scheduler()
    scheduler.stop_scheduler()


def test_scheduler_cleans_up_after_partial_start_failure(monkeypatch):
    class FailingScheduler:
        running = False
        shutdown_wait = None

        def start(self):
            self.running = True

        def modify_job(self, *args, **kwargs):
            raise RuntimeError("cannot schedule immediate poll")

        def shutdown(self, wait):
            self.shutdown_wait = wait
            self.running = False

    instance = FailingScheduler()
    monkeypatch.setattr(scheduler, "_build_scheduler", lambda: instance)

    with __import__("pytest").raises(RuntimeError, match="immediate poll"):
        scheduler.start_scheduler()

    assert instance.shutdown_wait is False


def test_scheduler_shutdown_waits_for_active_jobs(monkeypatch):
    class RunningScheduler:
        shutdown_wait = None

        def shutdown(self, wait):
            self.shutdown_wait = wait

    instance = RunningScheduler()
    monkeypatch.setattr(scheduler, "_scheduler", instance)

    scheduler.stop_scheduler()

    assert instance.shutdown_wait is True
    assert scheduler._scheduler is None