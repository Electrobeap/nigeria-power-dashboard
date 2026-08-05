import os
import logging
import platform
import re
import sys
import traceback

from flask import Flask, jsonify
from markupsafe import escape


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


_FALLBACK_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Nigeria Power Data | Temporarily unavailable</title>
<style>
 body{{margin:0;background:#F8FAFC;color:#0B1F3A;
      font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
 main{{max-width:640px;margin:0 auto;padding:64px 20px}}
 h1{{font-size:24px;margin:0 0 12px}}
 p{{color:#5B6B82;margin:0 0 16px}}
 code{{background:#EEF2F7;border-radius:4px;padding:2px 6px;font-size:13px}}
 a{{color:#2563EB}}
</style></head><body><main>
<h1>Nigeria Power Data is starting up</h1>
<p>The service could not initialise, so live grid metrics are unavailable for
   <code>{path}</code> right now. This page will work again once the deployment
   recovers.</p>
<p>Startup stage: <code>{stage}</code></p>
<p><a href="/api/health">Health diagnostics</a> &middot; <a href="/">Dashboard</a></p>
</main></body></html>"""


def _startup_fallback_app(error: Exception, stage: str, traceback_text: str) -> Flask:
    fallback = Flask(__name__)
    error_payload = _startup_error_payload(error, stage, traceback_text)

    @fallback.get("/api/health")
    def startup_health():
        return jsonify(error_payload), 503

    # Catch-all. Without it only "/" answered and every other URL - including
    # /state/<slug> - returned a bare 404, which hides a total startup failure
    # behind what looks like a routing bug.
    @fallback.get("/", defaults={"path": ""})
    @fallback.get("/<path:path>")
    def startup_failure(path):
        if path.startswith("api/"):
            return jsonify(error_payload), 503
        body = _FALLBACK_PAGE.format(path=escape(f"/{path}"), stage=escape(stage))
        return body, 503, {
            "Content-Type": "text/html; charset=utf-8",
            "Retry-After": "60",
            "Cache-Control": "no-store",
        }

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
