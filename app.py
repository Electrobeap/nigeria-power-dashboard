import os
import logging
import platform
import re
import sys
import traceback

from flask import Flask, jsonify


_startup_stage = "import_app"


def _startup_debug_enabled() -> bool:
    return os.environ.get("STARTUP_ERROR_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _redact_startup_message(message: str) -> str:
    return re.sub(
        r"(postgres(?:ql)?(?:\+\w+)?://)[^:@\s]+:[^@\s]+@",
        r"\1***:***@",
        message,
    )


def _startup_error_payload(error: Exception, stage: str, traceback_text: str) -> dict:
    payload = {
        "ok": False,
        "code": "startup_failed",
        "error_type": type(error).__name__,
        "error_message": _redact_startup_message(str(error)),
        "startup_stage": stage,
        "import_name": getattr(error, "name", None),
        "import_path": getattr(error, "path", None),
        "python_version": platform.python_version(),
        "message": "Application startup failed. Check Render logs for the traceback.",
    }
    if _startup_debug_enabled():
        payload["traceback_tail"] = traceback_text.splitlines()[-20:]
        payload["executable"] = sys.executable
    return payload


def _log_startup_failure(error: Exception, stage: str, traceback_text: str) -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("startup").error(
        "startup_failed stage=%s error_type=%s import_name=%s import_path=%s error=%s\n%s",
        stage,
        type(error).__name__,
        getattr(error, "name", None),
        getattr(error, "path", None),
        error,
        traceback_text,
    )


def _startup_fallback_app(error: Exception, stage: str, traceback_text: str) -> Flask:
    fallback = Flask(__name__)
    error_payload = _startup_error_payload(error, stage, traceback_text)

    @fallback.get("/")
    def startup_failure():
        return (
            "Nigeria Power Data startup failed. Check Render logs and /api/health.",
            503,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    @fallback.get("/api/health")
    def startup_health():
        return jsonify(error_payload), 503

    return fallback


try:
    _startup_stage = "import_grid_monitor_factory"
    from grid_monitor import create_app

    _startup_stage = "create_flask_app"
    app = create_app()
    _startup_stage = "ready"
except Exception as exc:
    formatted_traceback = traceback.format_exc()
    _log_startup_failure(exc, _startup_stage, formatted_traceback)
    app = _startup_fallback_app(exc, _startup_stage, formatted_traceback)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=debug)
