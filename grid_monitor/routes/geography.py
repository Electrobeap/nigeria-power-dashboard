from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from grid_monitor.extensions import db
from grid_monitor.models import DiscoData, GridSnapshot
from grid_monitor.services.articles import related_articles_for_context
from grid_monitor.services.cache import get_cached
from grid_monitor.services.entity_intelligence import slugify_entity
from grid_monitor.services.social_meta import build_social_meta
from grid_monitor.services.state_intelligence import (
    GEOGRAPHY_DEFAULT_HOURS,
    REGION_LABELS,
    STATE_PROFILES,
    GeographyNotFound,
    _analysis_summary,
    _combined_profile,
    _disco_key,
    _estimate_allocation,
    _forecast,
    _metrics,
    _moving_average,
    _profile_display,
    _region_state_slugs,
    _responsible_discos,
    _risk_classification,
    _stats,
    _trend,
    list_regions,
    list_states,
)
from grid_monitor.services.structured_data import build_structured_data
from grid_monitor.services.validation import bounded_float, bounded_int
from grid_monitor.utils.logging import log_event
from grid_monitor.utils.time import to_iso, utc_now, utc_now_iso


geo_fast_bp = Blueprint("geo_fast", __name__)
GEOGRAPHY_DEFAULT_LIMIT = 336
GEOGRAPHY_QUERY_MAX_LIMIT = 1200


def _effective_limit(limit: int | float | None) -> int:
    try:
        parsed = int(limit or GEOGRAPHY_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        parsed = GEOGRAPHY_DEFAULT_LIMIT
    return max(1, min(parsed, GEOGRAPHY_QUERY_MAX_LIMIT))


def _geography_cache_key(scope: str, slug: str, hours: float, limit: int) -> str:
    return f"geography:{scope}:{slug}:{hours}:{_effective_limit(limit)}"


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


def _static_analysis_summary(name: str, scope: str) -> str:
    return (
        f"{name} {scope.lower()} intelligence renders immediately from static franchise-area, population, demand-growth, "
        "and settlement-growth profiles. Live allocation trends, reliability movement, transformer risk, and peer rankings "
        "load asynchronously from stored public DisCo allocation readings when the analytics API responds."
    )


def _static_geography_context(scope: str, slug: str) -> dict[str, Any]:
    scope = slugify_entity(scope)
    slug = slugify_entity(slug)
    states_payload = None
    if scope == "state":
        profile = STATE_PROFILES.get(slug)
        if not profile:
            raise GeographyNotFound(f"State not found: {slug}")
        entity = {
            "name": profile["name"],
            "short_name": _profile_display(profile),
            "slug": slug,
            "region": REGION_LABELS[profile["region"]],
            "region_slug": profile["region"],
            "url": f"/state/{slug}",
        }
        related = list_states()
        peer_count = len(STATE_PROFILES)
        scope_label = "State"
    elif scope == "region":
        state_slugs = _region_state_slugs(slug)
        profile = _combined_profile(REGION_LABELS[slug], slug, state_slugs)
        entity = {
            "name": REGION_LABELS[slug],
            "short_name": REGION_LABELS[slug],
            "slug": slug,
            "region": REGION_LABELS[slug],
            "region_slug": slug,
            "url": f"/region/{slug}",
        }
        states_payload = [
            {"name": STATE_PROFILES[state_slug]["name"], "slug": state_slug, "url": f"/state/{state_slug}"}
            for state_slug in state_slugs
        ]
        related = list_regions()
        peer_count = len(REGION_LABELS)
        scope_label = "Region"
    else:
        raise GeographyNotFound(f"Geography scope not found: {scope}")

    payload = {
        "scope": scope,
        "entity": entity,
        "generated_at": utc_now_iso(),
        "window_hours": GEOGRAPHY_DEFAULT_HOURS,
        "sample_count": 0,
        "responsible_discos": _responsible_discos(profile),
        "current_allocation_components": [],
        "statistics": _stats([]),
        "metrics": _metrics(profile, None),
        "trend": _trend([]),
        "forecast": _forecast([]),
        "rankings": {
            "allocation_rank": None,
            "stress_rank": None,
            "reliability_rank": None,
            "peer_count": peer_count,
        },
        "risk": {"classification": "pending", "primary_driver": "historical_allocation_pending"},
        "history": [],
        "analysis_summary": _static_analysis_summary(entity["short_name"], scope_label),
        "related": related,
        "data_status": {
            "ok": False,
            "source": "static_geography_profile",
            "message": "Historical allocation analytics load asynchronously from the geography API.",
        },
    }
    if states_payload is not None:
        payload["states"] = states_payload
    return payload


def _allocation_rows(hours: float, limit: int, require_window: bool):
    effective_limit = _effective_limit(limit)
    snapshot_query = db.session.query(
        GridSnapshot.id.label("snapshot_id"),
        GridSnapshot.reading_timestamp.label("reading_timestamp"),
        GridSnapshot.captured_at.label("captured_at"),
    )
    if require_window:
        snapshot_query = snapshot_query.filter(GridSnapshot.reading_timestamp >= utc_now() - timedelta(hours=hours))
    snapshot_subquery = (
        snapshot_query.order_by(GridSnapshot.reading_timestamp.desc())
        .limit(effective_limit)
        .subquery()
    )
    return (
        db.session.query(
            snapshot_subquery.c.snapshot_id,
            snapshot_subquery.c.reading_timestamp,
            snapshot_subquery.c.captured_at,
            DiscoData.company,
            DiscoData.load_allocation_mw,
        )
        .outerjoin(DiscoData, DiscoData.snapshot_id == snapshot_subquery.c.snapshot_id)
        .order_by(snapshot_subquery.c.reading_timestamp.asc(), DiscoData.company.asc())
        .all()
    )


def _series_from_allocation_rows(rows) -> list[tuple[str | None, str | None, dict[str, float]]]:
    ordered_ids = []
    by_snapshot: dict[int, dict[str, Any]] = {}
    for row in rows:
        snapshot_id = row.snapshot_id
        if snapshot_id not in by_snapshot:
            ordered_ids.append(snapshot_id)
            by_snapshot[snapshot_id] = {
                "reading_timestamp": to_iso(row.reading_timestamp),
                "captured_at": to_iso(row.captured_at),
                "allocations": {},
            }
        key = _disco_key(row.company)
        if key and row.load_allocation_mw is not None:
            allocations = by_snapshot[snapshot_id]["allocations"]
            allocations[key] = allocations.get(key, 0.0) + float(row.load_allocation_mw)
    return [
        (
            by_snapshot[snapshot_id]["reading_timestamp"],
            by_snapshot[snapshot_id]["captured_at"],
            by_snapshot[snapshot_id]["allocations"],
        )
        for snapshot_id in ordered_ids
    ]


def _load_allocation_series(hours: float, limit: int) -> list[tuple[str | None, str | None, dict[str, float]]]:
    rows = _allocation_rows(hours, limit, require_window=True)
    if not rows:
        rows = _allocation_rows(hours, limit, require_window=False)
    return _series_from_allocation_rows(rows)


def _allocation_series(hours: float, limit: int) -> list[tuple[str | None, str | None, dict[str, float]]]:
    effective_limit = _effective_limit(limit)
    return get_cached(
        f"geography:allocations:{hours}:{effective_limit}",
        current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
        lambda: _load_allocation_series(hours, effective_limit),
    )


def _load_latest_allocation_context() -> dict[str, Any] | None:
    latest = (
        db.session.query(
            GridSnapshot.id.label("snapshot_id"),
            GridSnapshot.reading_timestamp.label("reading_timestamp"),
            GridSnapshot.captured_at.label("captured_at"),
        )
        .order_by(GridSnapshot.reading_timestamp.desc())
        .first()
    )
    if not latest:
        return None
    allocations: dict[str, float] = {}
    rows = (
        db.session.query(DiscoData.company, DiscoData.load_allocation_mw)
        .filter(DiscoData.snapshot_id == latest.snapshot_id)
        .all()
    )
    for row in rows:
        key = _disco_key(row.company)
        if key and row.load_allocation_mw is not None:
            allocations[key] = allocations.get(key, 0.0) + float(row.load_allocation_mw)
    return {
        "snapshot_id": latest.snapshot_id,
        "reading_timestamp": to_iso(latest.reading_timestamp),
        "captured_at": to_iso(latest.captured_at),
        "allocations": allocations,
    }


def _latest_allocation_context() -> dict[str, Any] | None:
    return get_cached(
        "geography:latest_allocation",
        current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
        _load_latest_allocation_context,
    )


def _history_for_profile(profile: dict[str, Any], hours: float, limit: int) -> list[dict[str, Any]]:
    history = []
    for reading_timestamp, captured_at, allocations in _allocation_series(hours, limit):
        allocation, components = _estimate_allocation(profile, allocations)
        metrics = _metrics(profile, allocation)
        history.append(
            {
                "timestamp": reading_timestamp,
                "captured_at": captured_at,
                "estimated_allocation_mw": round(allocation, 2) if allocation is not None else None,
                "estimated_peak_demand_mw": metrics["estimated_peak_demand_mw"],
                "power_availability_estimate_percent": metrics["power_availability_estimate_percent"],
                "grid_reliability_score": metrics["grid_reliability_score"],
                "infrastructure_stress_score": metrics["infrastructure_stress_score"],
                "components": components,
            }
        )
    return _moving_average(history)


def _rankings(target_slug: str, latest_allocations: dict[str, float] | None) -> dict[str, Any]:
    if not latest_allocations:
        return {"allocation_rank": None, "stress_rank": None, "reliability_rank": None, "peer_count": len(STATE_PROFILES)}
    rows = []
    for slug, profile in STATE_PROFILES.items():
        allocation, _ = _estimate_allocation(profile, latest_allocations)
        metrics = _metrics(profile, allocation)
        rows.append(
            {
                "slug": slug,
                "allocation": allocation or 0,
                "stress": metrics["infrastructure_stress_score"] if metrics["infrastructure_stress_score"] is not None else 101,
                "reliability": metrics["grid_reliability_score"] or 0,
            }
        )
    allocation_ranked = sorted(rows, key=lambda item: item["allocation"], reverse=True)
    stress_ranked = sorted(rows, key=lambda item: item["stress"])
    reliability_ranked = sorted(rows, key=lambda item: item["reliability"], reverse=True)
    return {
        "allocation_rank": next((idx for idx, row in enumerate(allocation_ranked, 1) if row["slug"] == target_slug), None),
        "stress_rank": next((idx for idx, row in enumerate(stress_ranked, 1) if row["slug"] == target_slug), None),
        "reliability_rank": next((idx for idx, row in enumerate(reliability_ranked, 1) if row["slug"] == target_slug), None),
        "peer_count": len(rows),
    }


def state_intelligence(slug: str, hours: float = GEOGRAPHY_DEFAULT_HOURS, limit: int = GEOGRAPHY_DEFAULT_LIMIT) -> dict[str, Any]:
    slug = slugify_entity(slug)
    profile = STATE_PROFILES.get(slug)
    if not profile:
        raise GeographyNotFound(f"State not found: {slug}")
    effective_limit = _effective_limit(limit)
    history = _history_for_profile(profile, hours, effective_limit)
    stats = _stats(history)
    metrics = _metrics(profile, stats["latest_mw"])
    latest_context = _latest_allocation_context()
    latest_allocations = latest_context["allocations"] if latest_context else None
    allocation, components = _estimate_allocation(profile, latest_allocations or {}) if latest_allocations else (None, [])
    trend = _trend(history)
    forecast = _forecast(history)
    rankings = _rankings(slug, latest_allocations)
    return {
        "scope": "state",
        "entity": {
            "name": profile["name"],
            "short_name": _profile_display(profile),
            "slug": slug,
            "region": REGION_LABELS[profile["region"]],
            "region_slug": profile["region"],
            "url": f"/state/{slug}",
        },
        "generated_at": utc_now_iso(),
        "window_hours": hours,
        "sample_count": len(history),
        "responsible_discos": _responsible_discos(profile),
        "current_allocation_components": components,
        "statistics": stats,
        "metrics": metrics,
        "trend": trend,
        "forecast": forecast,
        "rankings": rankings,
        "risk": {"classification": _risk_classification(metrics), "primary_driver": "infrastructure_stress"},
        "history": history,
        "analysis_summary": _analysis_summary(profile["name"], "State", stats, metrics, trend, rankings),
        "related": list_states(),
        "data_status": {"ok": True, "source": "stored_disco_allocation_history"},
    }


def region_intelligence(slug: str, hours: float = GEOGRAPHY_DEFAULT_HOURS, limit: int = GEOGRAPHY_DEFAULT_LIMIT) -> dict[str, Any]:
    slug = slugify_entity(slug)
    state_slugs = _region_state_slugs(slug)
    profile = _combined_profile(REGION_LABELS[slug], slug, state_slugs)
    effective_limit = _effective_limit(limit)
    history = _history_for_profile(profile, hours, effective_limit)
    stats = _stats(history)
    metrics = _metrics(profile, stats["latest_mw"])
    trend = _trend(history)
    forecast = _forecast(history)
    latest_context = _latest_allocation_context()
    latest_allocations = latest_context["allocations"] if latest_context else None
    allocation, components = _estimate_allocation(profile, latest_allocations or {}) if latest_allocations else (None, [])
    rankings = {"allocation_rank": None, "stress_rank": None, "reliability_rank": None, "peer_count": len(REGION_LABELS)}
    region_rows = []
    if latest_allocations:
        for region_slug, region_name in REGION_LABELS.items():
            combined = _combined_profile(region_name, region_slug, _region_state_slugs(region_slug))
            estimated, _ = _estimate_allocation(combined, latest_allocations)
            row_metrics = _metrics(combined, estimated)
            region_rows.append(
                {
                    "slug": region_slug,
                    "allocation": estimated or 0,
                    "stress": row_metrics["infrastructure_stress_score"] if row_metrics["infrastructure_stress_score"] is not None else 101,
                    "reliability": row_metrics["grid_reliability_score"] or 0,
                }
            )
        rankings = {
            "allocation_rank": next((idx for idx, row in enumerate(sorted(region_rows, key=lambda item: item["allocation"], reverse=True), 1) if row["slug"] == slug), None),
            "stress_rank": next((idx for idx, row in enumerate(sorted(region_rows, key=lambda item: item["stress"]), 1) if row["slug"] == slug), None),
            "reliability_rank": next((idx for idx, row in enumerate(sorted(region_rows, key=lambda item: item["reliability"], reverse=True), 1) if row["slug"] == slug), None),
            "peer_count": len(region_rows),
        }
    return {
        "scope": "region",
        "entity": {
            "name": REGION_LABELS[slug],
            "short_name": REGION_LABELS[slug],
            "slug": slug,
            "region": REGION_LABELS[slug],
            "region_slug": slug,
            "url": f"/region/{slug}",
        },
        "generated_at": utc_now_iso(),
        "window_hours": hours,
        "sample_count": len(history),
        "states": [
            {"name": STATE_PROFILES[state_slug]["name"], "slug": state_slug, "url": f"/state/{state_slug}"}
            for state_slug in state_slugs
        ],
        "responsible_discos": _responsible_discos(profile),
        "current_allocation_components": components,
        "statistics": stats,
        "metrics": metrics,
        "trend": trend,
        "forecast": forecast,
        "rankings": rankings,
        "risk": {"classification": _risk_classification(metrics), "primary_driver": "regional_infrastructure_stress"},
        "history": history,
        "analysis_summary": _analysis_summary(REGION_LABELS[slug], "Region", stats, metrics, trend, rankings),
        "related": list_regions(),
        "data_status": {"ok": True, "source": "stored_disco_allocation_history"},
    }


def _fast_seo_context(scope: str, slug: str) -> dict[str, Any]:
    payload = _static_geography_context(scope, slug)
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
            _geography_cache_key(scope, slug, hours, limit),
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
            fallback = _static_geography_context(scope, slug)
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
