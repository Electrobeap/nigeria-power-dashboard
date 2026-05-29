import os
import traceback

from flask import Flask, jsonify


def _startup_fallback_app(error: Exception) -> Flask:
    fallback = Flask(__name__)
    error_type = type(error).__name__

    @fallback.get("/")
    def startup_failure():
        return (
            "Nigeria Power Data startup failed. Check Render logs and /api/health.",
            503,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    @fallback.get("/api/health")
    def startup_health():
        return jsonify(
            {
                "ok": False,
                "code": "startup_failed",
                "error_type": error_type,
                "message": "Application startup failed. Check Render logs for the traceback.",
            }
        ), 503

    return fallback


try:
    from grid_monitor import create_app

    app = create_app()
except Exception as exc:
    traceback.print_exc()
    app = _startup_fallback_app(exc)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=debug)
