from __future__ import annotations

import logging
import time
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from grid_monitor.services.articles import related_articles_for_context
from grid_monitor.services.cache import get_cached
from grid_monitor.services.social_meta import build_social_meta
from grid_monitor.services.state_intelligence import (
    GEOGRAPHY_DEFAULT_HOURS,
    GEOGRAPHY_DEFAULT_LIMIT,
    GEOGRAPHY_QUERY_MAX_LIMIT,
    GeographyNotFound,
    geography_cache_key,
    region_intelligence,
    state_intelligence,
    static_geography_context,
)
from grid_monitor.services.structured_data import build_structured_data
from grid_monitor.services.validation import bounded_float, bounded_int
from grid_monitor.utils.logging import log_event
from grid_monitor.utils.time import utc_now_iso


geo_fast_bp = Blueprint("geo_fast", __name__)


def _timestamped(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("response_timestamp", utc_now_iso())
    return payload


def _json(payload: dict[str, Any], status: int = 200):
    return jsonify(_timestamped(payload)), status


def _format_mw(value, digits=0):
    if value is None:
        return "Loads asynchronously"
    return f"{float(value):,.{digits}f} MW"


def _format_percent(value, digits=1):
    if value is None:
        return "Loads asynchronously"
    return f"{float(value):,.{digits}f}%"


def _rank_value(rank, peer_count):
    return f"#{rank} of {peer_count}" if rank else "Loads asynchronously"


def _labelize(value):
    return str(value or "pending").replace("_", " ").replace("-", " ").title()


def _fast_seo_context(scope: str, slug: str) -> dict[str, Any]:
    payload = static_geography_context(scope, slug)
    entity = payload["entity"]
    name = entity.get("short_name") or entity["name"]
    metrics = payload.get("metrics") or {}
    stats = payload.get("statistics") or {}
    rankings = payload.get("rankings") or {}
    discos = payload.get("responsible_discos") or []
    disco_names = ", ".join(disco["name"] for disco in discos) or "DisCo coverage pending"
    scope_label = "State" if scope == "state" else "Regional"
    canonical_path = entity["url"]
    title = f"{name} Power Data: Allocation, Demand Growth & Grid Reliability"
    description = (
        f"{name} {scope_label.lower()} electricity intelligence covering responsible DisCos, estimated allocation, "
        "peak demand, demand growth, transformer risk, infrastructure stress, reliability score, and peer ranking."
    )
    facts = [
        {"label": "Responsible DisCo(s)", "value": disco_names},
        {"label": "Latest estimated allocation", "value": _format_mw(stats.get("latest_mw"))},
        {"label": "Estimated peak demand", "value": _format_mw(metrics.get("estimated_peak_demand_mw"))},
        {"label": "Demand growth", "value": _format_percent(metrics.get("estimated_demand_growth_percent"))},
        {"label": "Transformer risk score", "value": _labelize(payload.get("risk", {}).get("classification"))},
        {"label": "Reliability rank", "value": _rank_value(rankings.get("reliability_rank"), rankings.get("peer_count"))},
    ]
    faq_items = [
        {
            "question": f"Which DisCos serve {name}?",
            "answer": f"{name} is mapped to {disco_names} in Nigeria Power Data's planning-grade franchise coverage model.",
        },
        {
            "question": f"Why does the {name} page load before all analytics appear?",
            "answer": "The page renders immediately from static geography metadata, then loads detailed historical allocation, risk, trend, and ranking analytics asynchronously from stored public readings.",
        },
        {
            "question": f"How should {name} transformer risk be interpreted?",
            "answer": "Transformer risk is a planning indicator based on allocation pressure, infrastructure stress, settlement growth, and demand assumptions. It is not direct feeder or transformer telemetry.",
        },
    ]
    breadcrumbs = [
        {"name": "Home", "path": "/"},
        {"name": "States" if scope == "state" else "Regions", "path": "/states" if scope == "state" else "/regions"},
        {"name": name, "path": canonical_path},
    ]
    return {
        "payload": payload,
        "title": title,
        "description": description,
        "canonical_path": canonical_path,
        "breadcrumbs": breadcrumbs,
        "sections": ["Allocation trend", "Demand growth", "Transformer risk", "Reliability ranking"],
        "faq_items": faq_items,
        "content": {
            "eyebrow": f"{scope_label} Intelligence",
            "h1": title,
            "lede": description,
            "summary": payload.get("analysis_summary"),
            "facts": facts,
            "faq_items": faq_items,
            "breadcrumbs": breadcrumbs,
        },
    }


def _report_schema(title, description, path, breadcrumbs, sections, faq_items=None):
    return build_structured_data(
        title=title,
        description=description,
        path=path,
        breadcrumbs=breadcrumbs,
        page_type="WebPage",
        article_type="Article",
        article_sections=sections,
        faq_items=faq_items,
    )


def _render_geo_page(scope: str, api_collection: str, slug: str):
    started = time.perf_counter()
    log_event("geo_fast_page_started", logging.INFO, scope=scope, slug=slug)
    try:
        seo = _fast_seo_context(scope, slug)
    except GeographyNotFound:
        log_event(
            "geo_fast_page_rejected",
            logging.INFO,
            scope=scope,
            slug=slug,
            status=404,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        abort(404)
    response = render_template(
        "geo.html",
        scope=scope,
        api_collection=api_collection,
        slug=slug,
        canonical_path=seo["canonical_path"],
        page_title=seo["title"],
        description=seo["description"],
        seo_content=seo["content"],
        related_articles=related_articles_for_context(scope, slug),
        social_meta=build_social_meta(seo["title"], seo["description"], seo["canonical_path"], og_type="article"),
        structured_data=_report_schema(
            seo["title"],
            seo["description"],
            seo["canonical_path"],
            seo["breadcrumbs"],
            seo["sections"],
            faq_items=seo["faq_items"],
        ),
    )
    log_event(
        "geo_fast_page_served",
        logging.INFO,
        scope=scope,
        slug=slug,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return response


@geo_fast_bp.get("/state/<slug>")
def fast_state_page(slug):
    return _render_geo_page("state", "states", slug)


@geo_fast_bp.get("/region/<slug>")
def fast_region_page(slug):
    return _render_geo_page("region", "regions", slug)


def _effective_api_limit(hours: float) -> int:
    limit = bounded_int(request.args.get("limit"), GEOGRAPHY_DEFAULT_LIMIT, 1, GEOGRAPHY_QUERY_MAX_LIMIT)
    if hours <= GEOGRAPHY_DEFAULT_HOURS and limit > GEOGRAPHY_DEFAULT_LIMIT:
        return GEOGRAPHY_DEFAULT_LIMIT
    return limit


def _geography_api_response(scope: str, slug: str):
    started = time.perf_counter()
    hours = bounded_float(request.args.get("hours"), GEOGRAPHY_DEFAULT_HOURS, 1, 720)
    limit = _effective_api_limit(hours)
    loader = state_intelligence if scope == "state" else region_intelligence
    try:
        payload = get_cached(
            geography_cache_key(scope, slug, hours, limit),
            current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
            lambda: loader(slug, hours, limit),
        )
        payload.setdefault("performance", {})["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return _json(payload)
    except GeographyNotFound as exc:
        return _json({"error": str(exc), "code": "geography_not_found", "status": 404}, 404)
    except Exception as exc:
        current_app.logger.exception(
            {"event": "geography_api_failed", "scope": scope, "slug": slug, "error": str(exc)}
        )
        try:
            fallback = static_geography_context(scope, slug)
        except GeographyNotFound as not_found:
            return _json({"error": str(not_found), "code": "geography_not_found", "status": 404}, 404)
        fallback["data_status"] = {
            "ok": False,
            "source": "static_geography_profile",
            "message": "Historical allocation analytics are temporarily unavailable; static planning indicators are shown.",
            "error_type": type(exc).__name__,
        }
        fallback.setdefault("performance", {})["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return _json(fallback)


@geo_fast_bp.get("/api/states/<slug>")
def fast_state_detail(slug):
    return _geography_api_response("state", slug)


@geo_fast_bp.get("/api/regions/<slug>")
def fast_region_detail(slug):
    return _geography_api_response("region", slug)
