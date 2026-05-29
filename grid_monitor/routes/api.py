import copy
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from grid_monitor.services.analytics import enrich_history_payload, history_analytics, multi_window_analytics
from grid_monitor.services.cache import get_cached
from grid_monitor.services.distribution import distribution_intelligence
from grid_monitor.services.entity_intelligence import EntityNotFound, entity_intelligence, list_entities
from grid_monitor.services.scheduler import scheduler_status
from grid_monitor.services.scraper import get_dashboard_payload, get_disco_profile, get_live_grid_payload
from grid_monitor.services.storage import (
    get_history_points,
    get_latest_snapshot,
    save_grid_snapshot,
    storage_status,
)
from grid_monitor.services.validation import ValidationError, bounded_float, bounded_int
from grid_monitor.utils.time import utc_now_iso


api_bp = Blueprint("api", __name__)


def _timestamped(payload: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(payload)
    payload.setdefault("response_timestamp", utc_now_iso())
    return payload


def _json(payload: dict[str, Any], status: int = 200):
    return jsonify(_timestamped(payload)), status


def _error(message: str, status: int = 500, code: str = "internal_error"):
    return _json({"error": message, "code": code, "status": status}, status)


def _entity_response(entity_type: str, slug: str):
    hours = bounded_float(request.args.get("hours"), 168, 1, 720)
    limit = bounded_int(request.args.get("limit"), 1000, 1, 5000)
    try:
        return _json(
            get_cached(
                f"entity:{entity_type}:{slug}:{hours}:{limit}",
                current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
                lambda: entity_intelligence(entity_type, slug, hours, limit),
            )
        )
    except EntityNotFound as exc:
        return _error(str(exc), 404, "entity_not_found")


def _fallback_latest(error: Exception) -> dict[str, Any] | None:
    latest = get_latest_snapshot()
    if not latest:
        return None
    latest["stale"] = True
    latest["source_error"] = str(error)
    return latest


@api_bp.errorhandler(ValidationError)
def handle_validation_error(exc: ValidationError):
    return _error(str(exc), 400, "validation_error")


@api_bp.errorhandler(Exception)
def handle_unexpected_error(exc: Exception):
    current_app.logger.exception({"event": "api_unhandled_error", "error": str(exc)})
    return _error("Internal server error", 500, "internal_error")


@api_bp.get("/data")
def legacy_data():
    try:
        data = get_live_grid_payload()
    except Exception as exc:
        data = get_latest_snapshot()
        if not data:
            return _error(str(exc), 503, "source_unavailable")

    return _json(
        {
            "total_generation_mw": data["total_generation_mw"],
            "timestamp": data["as_at_time"],
            "source": data["source"],
            "source_url": data["source_url"],
            "fetched_at": data["fetched_at"],
            "reporting_gencos": data["reporting_gencos"],
        }
    )


@api_bp.get("/api/grid/live")
def live_grid():
    try:
        return _json(get_live_grid_payload())
    except Exception as exc:
        fallback = _fallback_latest(exc)
        if fallback:
            return _json(fallback)
        return _error(str(exc), 503, "source_unavailable")


@api_bp.get("/api/grid/gencos")
def grid_gencos():
    try:
        data = get_dashboard_payload()
        return _json(
            {
                "gencos": data["gencos"],
                "source": data["source"],
                "source_url": data["source_url"],
                "fetched_at": data["fetched_at"],
                "stale": data.get("stale", False),
            }
        )
    except Exception as exc:
        fallback = get_latest_snapshot()
        if fallback and fallback["gencos"]:
            return _json(
                {
                    "gencos": fallback["gencos"],
                    "source": fallback["source"],
                    "source_url": fallback["source_url"],
                    "fetched_at": fallback["fetched_at"],
                    "reading_timestamp": fallback["reading_timestamp"],
                    "stale": True,
                    "source_error": str(exc),
                }
            )
        return _error(str(exc), 503, "source_unavailable")


@api_bp.get("/api/grid/discos")
def grid_discos():
    try:
        return _json(get_disco_profile())
    except Exception as exc:
        fallback = get_latest_snapshot()
        if fallback and fallback["disco_profile"]["discos"]:
            profile = fallback["disco_profile"]
            profile["reading_timestamp"] = fallback["reading_timestamp"]
            profile["stale"] = True
            profile["source_error"] = str(exc)
            return _json(profile)
        return _error(str(exc), 503, "source_unavailable")


@api_bp.get("/api/latest")
def latest():
    snapshot = get_latest_snapshot()
    if snapshot:
        snapshot["analytics"] = get_cached(
            f"analytics:latest:{snapshot['reading_timestamp']}",
            current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            lambda: multi_window_analytics(
                get_history_points(24, 288),
                get_history_points(168, 2016),
                snapshot,
            ),
        )
        return _json(snapshot)

    try:
        live = get_live_grid_payload()
        save_grid_snapshot(live)
        snapshot = get_latest_snapshot()
        if snapshot:
            snapshot["analytics"] = multi_window_analytics(
                get_history_points(24, 288),
                get_history_points(168, 2016),
                snapshot,
            )
        return _json(snapshot or live)
    except Exception as exc:
        return _error(str(exc), 503, "source_unavailable")


@api_bp.get("/api/history")
def history():
    hours = bounded_float(request.args.get("hours"), 24, 1, 168)
    limit = bounded_int(request.args.get("limit"), 288, 1, 2000)

    def load_payload():
        latest_snapshot = get_latest_snapshot()
        points = get_history_points(hours, limit)
        return enrich_history_payload(points, hours, limit, latest_snapshot)

    return _json(
        get_cached(
            f"history:{hours}:{limit}",
            current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            load_payload,
        )
    )


@api_bp.get("/api/discos")
def discos():
    snapshot = get_latest_snapshot()
    if snapshot and snapshot["disco_profile"]["discos"]:
        profile = snapshot["disco_profile"]
        profile["reading_timestamp"] = snapshot["reading_timestamp"]
        return _json(profile)

    try:
        return _json(get_disco_profile())
    except Exception as exc:
        return _error(str(exc), 503, "source_unavailable")


@api_bp.get("/api/gencos")
def gencos():
    snapshot = get_latest_snapshot()
    if snapshot and snapshot["gencos"]:
        return _json(
            {
                "gencos": snapshot["gencos"],
                "source": snapshot["source"],
                "source_url": snapshot["source_url"],
                "fetched_at": snapshot["fetched_at"],
                "reading_timestamp": snapshot["reading_timestamp"],
            }
        )

    try:
        data = get_dashboard_payload()
        return _json(
            {
                "gencos": data["gencos"],
                "source": data["source"],
                "source_url": data["source_url"],
                "fetched_at": data["fetched_at"],
            }
        )
    except Exception as exc:
        return _error(str(exc), 503, "source_unavailable")


@api_bp.get("/api/analytics")
def analytics():
    hours = bounded_float(request.args.get("hours"), 24, 1, 168)
    limit = bounded_int(request.args.get("limit"), 288, 1, 2000)

    def load_payload():
        latest_snapshot = get_latest_snapshot()
        points = get_history_points(hours, limit)
        points_24h = get_history_points(24, 288)
        points_7d = get_history_points(168, 2016)
        return {
            "hours": hours,
            "limit": limit,
            "analytics": history_analytics(points, hours, latest_snapshot),
            "windows": multi_window_analytics(points_24h, points_7d, latest_snapshot),
        }

    return _json(
        get_cached(
            f"analytics:{hours}:{limit}",
            current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            load_payload,
        )
    )


@api_bp.get("/api/metadata")
def metadata():
    endpoints = {
        "live": "/api/grid/live",
        "latest": "/api/latest",
        "history": "/api/history?hours=24&limit=288",
        "analytics": "/api/analytics",
        "distribution": "/api/distribution?hours=168&limit=336",
        "disco_entity": "/api/discos/{slug}?hours=168&limit=1000",
        "genco_entity": "/api/gencos/{slug}?hours=168&limit=1000",
        "gencos": "/api/gencos",
        "discos": "/api/discos",
        "health": "/api/health",
    }
    return _json(
        {
            "name": current_app.config["API_NAME"],
            "version": current_app.config["API_VERSION"],
            "timezone": "UTC",
            "source": {
                "dashboard_url": current_app.config["NIGGRID_DASHBOARD_URL"],
                "disco_url": current_app.config["NIGGRID_DISCO_URL"],
                "cache_ttl_seconds": current_app.config["GRID_CACHE_TTL_SECONDS"],
            },
            "storage": {
                "database_uri": current_app.config["SAFE_DATABASE_URI"],
                "capture_interval_seconds": current_app.config["HISTORY_CAPTURE_INTERVAL_SECONDS"],
                "analytics_cache_ttl_seconds": current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            },
            "endpoints": endpoints,
        }
    )


@api_bp.get("/api/entities")
def entities():
    return _json({"discos": list_entities("disco"), "gencos": list_entities("genco")})


@api_bp.get("/api/discos/<slug>")
def disco_detail(slug):
    return _entity_response("disco", slug)


@api_bp.get("/api/gencos/<slug>")
def genco_detail(slug):
    return _entity_response("genco", slug)


@api_bp.get("/api/distribution")
def distribution():
    hours = bounded_float(request.args.get("hours"), 168, 1, 168)
    limit = bounded_int(request.args.get("limit"), 336, 1, 2000)
    latest_snapshot = get_latest_snapshot()
    if not latest_snapshot:
        return _error("No stored DisCo allocation data available yet", 503, "distribution_unavailable")

    return _json(
        get_cached(
            f"distribution:{latest_snapshot['reading_timestamp']}:{hours}:{limit}",
            current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            lambda: distribution_intelligence(
                latest_snapshot,
                get_history_points(hours, limit),
                hours,
            ),
        )
    )


@api_bp.get("/api/health")
def health():
    storage = storage_status()
    status = {
        "ok": storage["ok"],
        "database": storage,
        "capture": {
            **scheduler_status(),
            "enabled": current_app.config["HISTORY_CAPTURE_ENABLED"],
            "interval_seconds": current_app.config["HISTORY_CAPTURE_INTERVAL_SECONDS"],
        },
        "source": {
            "timeout_seconds": current_app.config["GRID_SOURCE_TIMEOUT_SECONDS"],
            "retries": current_app.config["GRID_SCRAPER_RETRIES"],
            "cache_ttl_seconds": current_app.config["GRID_CACHE_TTL_SECONDS"],
        },
        "api": {
            "name": current_app.config["API_NAME"],
            "version": current_app.config["API_VERSION"],
        },
    }
    return _json(status, 200 if storage["ok"] else 503)
