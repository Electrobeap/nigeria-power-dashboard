import secrets
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from grid_monitor.services.analytics import enrich_history_payload, history_analytics, multi_window_analytics
from grid_monitor.services.cache import cache_status, get_cached
from grid_monitor.services.distribution import distribution_intelligence
from grid_monitor.services.entity_intelligence import EntityNotFound, entity_intelligence, list_entities
from grid_monitor.services.geographic_hierarchy import (
    HierarchyNotFound,
    hierarchy_counts,
    hierarchy_detail,
    hierarchy_overview,
    search_hierarchy,
)
from grid_monitor.services.indexnow import (
    indexnow_status,
    submit_indexnow_urls,
    submit_public_urls_if_due,
)
from grid_monitor.services.scheduler import scheduler_status
from grid_monitor.services.scraper import get_dashboard_payload, get_disco_profile, get_live_grid_payload
from grid_monitor.services.state_intelligence import (
    GeographyNotFound,
    list_regions,
    list_states,
    region_intelligence,
    state_intelligence,
)
from grid_monitor.services.storage import (
    get_history_points,
    get_latest_snapshot,
    save_grid_snapshot,
    storage_status,
)
from grid_monitor.services.validation import ValidationError, bounded_float, bounded_int
from grid_monitor.utils.memory import process_memory_status
from grid_monitor.utils.time import utc_now_iso


api_bp = Blueprint("api", __name__)


def _timestamped(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("response_timestamp", utc_now_iso())
    return payload


def _json(payload: dict[str, Any], status: int = 200):
    return jsonify(_timestamped(payload)), status


def _error(message: str, status: int = 500, code: str = "internal_error"):
    return _json({"error": message, "code": code, "status": status}, status)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _indexnow_authorized() -> bool:
    expected = current_app.config.get("INDEXNOW_ADMIN_TOKEN")
    if not expected:
        return False
    authorization = request.headers.get("Authorization", "")
    bearer_token = authorization.removeprefix("Bearer ").strip()
    submitted = request.headers.get("X-IndexNow-Token") or bearer_token
    return bool(submitted) and secrets.compare_digest(str(submitted), str(expected))


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


def _geography_response(scope: str, slug: str):
    hours = bounded_float(request.args.get("hours"), 168, 1, 720)
    limit = bounded_int(request.args.get("limit"), 1000, 1, 5000)
    loader = state_intelligence if scope == "state" else region_intelligence
    try:
        return _json(
            get_cached(
                f"geography:{scope}:{slug}:{hours}:{limit}",
                current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
                lambda: loader(slug, hours, limit),
            )
        )
    except GeographyNotFound as exc:
        return _error(str(exc), 404, "geography_not_found")


def _hierarchy_response(level: str, slug: str):
    try:
        return _json(
            get_cached(
                f"hierarchy:{level}:{slug}",
                current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
                lambda: hierarchy_detail(level, slug),
            )
        )
    except HierarchyNotFound as exc:
        return _error(str(exc), 404, "hierarchy_not_found")


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


@api_bp.get("/api/generation")
def generation():
    hours = bounded_float(request.args.get("hours"), 24, 1, 168)
    limit = bounded_int(request.args.get("limit"), 288, 1, 2000)

    def load_payload():
        latest_snapshot = get_latest_snapshot()
        points = get_history_points(hours, limit)
        history_payload = enrich_history_payload(points, hours, limit, latest_snapshot)
        return {
            "hours": hours,
            "limit": limit,
            "latest": {
                "snapshot_id": latest_snapshot.get("snapshot_id"),
                "reading_timestamp": latest_snapshot.get("reading_timestamp"),
                "total_generation_mw": latest_snapshot.get("total_generation_mw"),
                "reporting_gencos": latest_snapshot.get("reporting_gencos"),
                "source": latest_snapshot.get("source"),
                "source_url": latest_snapshot.get("source_url"),
                "fetched_at": latest_snapshot.get("fetched_at"),
            }
            if latest_snapshot
            else None,
            "generation": history_payload,
        }

    return _json(
        get_cached(
            f"generation:{hours}:{limit}",
            current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            load_payload,
        )
    )


@api_bp.get("/api/market-data")
def market_data():
    snapshot = get_latest_snapshot()
    if not snapshot:
        try:
            live = get_live_grid_payload()
            save_grid_snapshot(live)
            snapshot = get_latest_snapshot()
        except Exception as exc:
            return _error(str(exc), 503, "source_unavailable")

    points_24h = get_history_points(24, 288)
    points_7d = get_history_points(168, 2016)
    analytics = multi_window_analytics(points_24h, points_7d, snapshot)
    return _json(
        {
            "latest": snapshot,
            "generation": enrich_history_payload(points_24h, 24, 288, snapshot),
            "analytics": analytics,
            "daily": snapshot.get("daily") or {},
            "gencos": snapshot.get("gencos") or [],
            "discos": (snapshot.get("disco_profile") or {}).get("discos") or [],
            "disco_profile": snapshot.get("disco_profile") or {},
            "source": {
                "name": snapshot.get("source"),
                "url": snapshot.get("source_url"),
                "fetched_at": snapshot.get("fetched_at"),
                "reading_timestamp": snapshot.get("reading_timestamp"),
            },
        }
    )


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
        "generation": "/api/generation?hours=24&limit=288",
        "market_data": "/api/market-data",
        "analytics": "/api/analytics",
        "distribution": "/api/distribution?hours=168&limit=336",
        "disco_entity": "/api/discos/{slug}?hours=168&limit=1000",
        "genco_entity": "/api/gencos/{slug}?hours=168&limit=1000",
        "states": "/api/states",
        "state": "/api/states/{slug}?hours=168&limit=1000",
        "regions": "/api/regions",
        "region": "/api/regions/{slug}?hours=168&limit=1000",
        "geography_map": "/api/geography/map",
        "geography_search": "/api/geography/search?q=lagos",
        "geography_hierarchy": "/api/geography/{level}/{slug}",
        "indexnow": "/api/indexnow",
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
            "geography_hierarchy": {
                "levels": ["state", "lga", "town", "community", "settlement"],
                "counts": hierarchy_counts(),
                "dataset_path": current_app.config.get("GEOGRAPHY_DATASET_PATH"),
            },
            "endpoints": endpoints,
        }
    )


@api_bp.get("/api/indexnow")
def indexnow_metadata():
    return _json(indexnow_status())


@api_bp.post("/api/indexnow")
def indexnow_submit():
    payload = request.get_json(silent=True) or {}
    dry_run = _truthy(payload.get("dry_run")) or _truthy(request.args.get("dry_run"))
    force = _truthy(payload.get("force")) or _truthy(request.args.get("force"))
    urls = payload.get("urls")
    if urls is not None and (
        not isinstance(urls, list) or any(not isinstance(url, str) for url in urls)
    ):
        raise ValidationError("urls must be a list of absolute URL strings")
    if not dry_run and not _indexnow_authorized():
        return _error("INDEXNOW_ADMIN_TOKEN is required for manual submissions", 403, "forbidden")

    try:
        if urls:
            result = submit_indexnow_urls(urls, reason="api", dry_run=dry_run)
        else:
            result = (
                submit_indexnow_urls(reason="api", dry_run=True)
                if dry_run
                else submit_public_urls_if_due(force=force, reason="api")
            )
    except Exception as exc:
        return _error(str(exc), 502, "indexnow_submission_failed")

    status = 200 if result.get("ok") else 502
    return _json(result, status)


@api_bp.get("/api/entities")
def entities():
    return _json(
        {
            "discos": list_entities("disco"),
            "gencos": list_entities("genco"),
            "states": list_states(),
            "regions": list_regions(),
        }
    )


@api_bp.get("/api/geography/map")
def geography_map():
    return _json(
        get_cached(
            "hierarchy:map",
            current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            hierarchy_overview,
        )
    )


@api_bp.get("/api/geography/search")
def geography_search():
    limit = bounded_int(request.args.get("limit"), 20, 1, 50)
    return _json(search_hierarchy(request.args.get("q", ""), request.args.get("level"), limit))


@api_bp.get("/api/geography/<level>/<slug>")
def geography_hierarchy_detail(level, slug):
    return _hierarchy_response(level, slug)


@api_bp.get("/api/states")
def states():
    return _json({"states": list_states(), "regions": list_regions()})


@api_bp.get("/api/states/<slug>")
def state_detail(slug):
    return _geography_response("state", slug)


@api_bp.get("/api/regions")
def regions():
    return _json({"regions": list_regions()})


@api_bp.get("/api/regions/<slug>")
def region_detail(slug):
    return _geography_response("region", slug)


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
            "web_scheduler_enabled": current_app.config["WEB_SCHEDULER_ENABLED"],
            "capture_on_startup": current_app.config["HISTORY_CAPTURE_ON_STARTUP"],
            "interval_seconds": current_app.config["HISTORY_CAPTURE_INTERVAL_SECONDS"],
        },
        "source": {
            "timeout_seconds": current_app.config["GRID_SOURCE_TIMEOUT_SECONDS"],
            "retries": current_app.config["GRID_SCRAPER_RETRIES"],
            "cache_ttl_seconds": current_app.config["GRID_CACHE_TTL_SECONDS"],
        },
        "memory": process_memory_status(current_app.config["MEMORY_LIMIT_MB"]),
        "cache": cache_status(),
        "api": {
            "name": current_app.config["API_NAME"],
            "version": current_app.config["API_VERSION"],
        },
        "indexnow": indexnow_status(),
    }
    return _json(status, 200 if storage["ok"] else 503)
