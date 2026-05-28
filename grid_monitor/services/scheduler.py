import logging
import os
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from grid_monitor.services.analytics import history_analytics
from grid_monitor.services.cache import clear_cache
<<<<<<< HEAD
=======
from grid_monitor.services.distribution import distribution_intelligence
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
from grid_monitor.services.scraper import get_live_grid_payload
from grid_monitor.services.storage import (
    get_history_points,
    get_latest_snapshot,
    save_analytics_snapshot,
<<<<<<< HEAD
=======
    save_distribution_snapshot,
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
    save_grid_snapshot,
)
from grid_monitor.utils.logging import log_event


JOB_ID = "niggrid-history-capture"
_scheduler: BackgroundScheduler | None = None
_status: dict[str, Any] = {
    "started": False,
    "running": False,
    "job_id": JOB_ID,
    "last_run_at": None,
    "last_success_at": None,
    "last_error": None,
    "last_result": None,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_analytics_snapshots() -> list[dict[str, Any]]:
    latest = get_latest_snapshot()
    if not latest:
        return []

    points_24h = get_history_points(24, 288)
    points_7d = get_history_points(168, 2016)
    analytics_24h = history_analytics(points_24h, 24, latest)
    analytics_7d = history_analytics(points_7d, 168, latest)
<<<<<<< HEAD
    return [
        save_analytics_snapshot(latest["snapshot_id"], 24, analytics_24h),
        save_analytics_snapshot(latest["snapshot_id"], 168, analytics_7d),
=======
    distribution_24h = distribution_intelligence(latest, points_24h, 24)
    distribution_7d = distribution_intelligence(latest, points_7d, 168)
    return [
        save_analytics_snapshot(latest["snapshot_id"], 24, analytics_24h),
        save_analytics_snapshot(latest["snapshot_id"], 168, analytics_7d),
        save_distribution_snapshot(latest["snapshot_id"], 24, distribution_24h),
        save_distribution_snapshot(latest["snapshot_id"], 168, distribution_7d),
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
    ]


def capture_once(app) -> dict[str, Any]:
    with app.app_context():
        _status["running"] = True
        _status["last_run_at"] = _iso_now()
        try:
            payload = get_live_grid_payload()
            result = save_grid_snapshot(payload)
            analytics_results = _record_analytics_snapshots()
            clear_cache()
            result["analytics_snapshots"] = analytics_results
            _status["last_success_at"] = _iso_now()
            _status["last_error"] = None
            _status["last_result"] = result
            log_event(
                "history_capture_complete",
                inserted=result["inserted"],
                snapshot_id=result["snapshot_id"],
                reading_timestamp=result["reading_timestamp"],
                analytics_snapshots=analytics_results,
            )
            return result
        except Exception as exc:
            _status["last_error"] = str(exc)
            log_event("history_capture_failed", logging.ERROR, error=str(exc))
            raise
        finally:
            _status["running"] = False


def _should_start(app) -> bool:
    if not app.config["HISTORY_CAPTURE_ENABLED"]:
        return False
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def start_scheduler(app) -> None:
    global _scheduler
    if not _should_start(app):
        return

    if _scheduler and _scheduler.running:
        if not _scheduler.get_job(JOB_ID):
            _scheduler.add_job(
                capture_once,
                trigger=IntervalTrigger(seconds=app.config["HISTORY_CAPTURE_INTERVAL_SECONDS"]),
                args=[app],
                id=JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=120,
            )
        return

    _scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    _scheduler.add_job(
        capture_once,
        trigger=IntervalTrigger(seconds=app.config["HISTORY_CAPTURE_INTERVAL_SECONDS"]),
        args=[app],
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    _scheduler.start()
    _status["started"] = True
    log_event(
        "apscheduler_started",
        job_id=JOB_ID,
        interval_seconds=app.config["HISTORY_CAPTURE_INTERVAL_SECONDS"],
    )

    if app.config["HISTORY_CAPTURE_ON_STARTUP"]:
        try:
            capture_once(app)
        except Exception as exc:
            log_event("startup_capture_failed", logging.WARNING, error=str(exc))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log_event("apscheduler_stopped", job_id=JOB_ID)


def scheduler_status() -> dict[str, Any]:
    status = dict(_status)
    if _scheduler:
        job = _scheduler.get_job(JOB_ID)
        status.update(
            {
                "scheduler_running": _scheduler.running,
                "job_exists": job is not None,
                "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
            }
        )
    else:
        status.update({"scheduler_running": False, "job_exists": False, "next_run_at": None})
    return status
