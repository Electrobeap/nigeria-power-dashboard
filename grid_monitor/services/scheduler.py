import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from grid_monitor.services.scraper import get_live_grid_payload
from grid_monitor.services.storage import save_grid_snapshot
from grid_monitor.utils.logging import log_event


_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_status: dict[str, Any] = {
    "started": False,
    "running": False,
    "last_run_at": None,
    "last_success_at": None,
    "last_error": None,
    "last_result": None,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_once(app) -> dict[str, Any]:
    with app.app_context():
        _status["last_run_at"] = _iso_now()
        payload = get_live_grid_payload()
        result = save_grid_snapshot(payload)
        _status["last_success_at"] = _iso_now()
        _status["last_error"] = None
        _status["last_result"] = result
        log_event(
            "history_capture_complete",
            inserted=result["inserted"],
            snapshot_id=result["snapshot_id"],
            reading_timestamp=result["reading_timestamp"],
        )
        return result


def _capture_loop(app) -> None:
    _status["running"] = True
    interval = app.config["HISTORY_CAPTURE_INTERVAL_SECONDS"]
    log_event("history_capture_started", interval_seconds=interval)

    if app.config["HISTORY_CAPTURE_ON_STARTUP"]:
        try:
            capture_once(app)
        except Exception as exc:
            _status["last_run_at"] = _iso_now()
            _status["last_error"] = str(exc)
            log_event("history_capture_failed", logging.ERROR, error=str(exc))

    while not _stop_event.wait(interval):
        try:
            capture_once(app)
        except Exception as exc:
            _status["last_run_at"] = _iso_now()
            _status["last_error"] = str(exc)
            log_event("history_capture_failed", logging.ERROR, error=str(exc))

    _status["running"] = False
    log_event("history_capture_stopped")


def _should_start(app) -> bool:
    if not app.config["HISTORY_CAPTURE_ENABLED"]:
        return False
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def start_scheduler(app) -> None:
    global _thread
    if not _should_start(app):
        return
    with _lock:
        if _thread and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(
            target=_capture_loop,
            args=(app,),
            name="grid-history-capture",
            daemon=True,
        )
        _thread.start()
        _status["started"] = True


def stop_scheduler() -> None:
    _stop_event.set()


def scheduler_status() -> dict[str, Any]:
    return dict(_status)
