import math
import re
from datetime import timedelta
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import func

from grid_monitor.extensions import db
from grid_monitor.models import DiscoData, GencoData, GridSnapshot
from grid_monitor.services.distribution import distribution_intelligence
from grid_monitor.services.storage import get_history_points, get_latest_snapshot
from grid_monitor.utils.time import parse_iso_datetime, to_iso, utc_now, utc_now_iso


ENTITY_META = {
    "disco": {
        "plural": "discos",
        "label": "DisCo",
        "model": DiscoData,
        "name_attr": "company",
        "value_attr": "load_allocation_mw",
        "unit": "MW allocation",
    },
    "genco": {
        "plural": "gencos",
        "label": "GenCo",
        "model": GencoData,
        "name_attr": "plant",
        "value_attr": "generation_mw",
        "unit": "MW output",
    },
}


class EntityNotFound(ValueError):
    pass


def slugify_entity(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return cleaned.strip("-") or "unknown"


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _entity_meta(entity_type: str) -> dict[str, Any]:
    try:
        return ENTITY_META[entity_type]
    except KeyError as exc:
        raise EntityNotFound(f"Unsupported entity type: {entity_type}") from exc


def _all_entity_names(entity_type: str) -> list[str]:
    meta = _entity_meta(entity_type)
    model = meta["model"]
    name_col = getattr(model, meta["name_attr"])
    rows = db.session.query(name_col).filter(name_col.isnot(None)).distinct().all()
    names = sorted({row[0] for row in rows if row[0]}, key=str.lower)

    latest = get_latest_snapshot()
    if latest:
        if entity_type == "disco":
            latest_rows = (latest.get("disco_profile") or {}).get("discos") or []
            names.extend(row["company"] for row in latest_rows if row.get("company"))
        else:
            names.extend(row["plant"] for row in latest.get("gencos") or [] if row.get("plant"))

    return sorted(set(names), key=str.lower)


def resolve_entity_name(entity_type: str, slug: str) -> str:
    requested = slug.strip().lower()
    for name in _all_entity_names(entity_type):
        if slugify_entity(name) == requested or name.lower() == requested:
            return name
    raise EntityNotFound(f"{_entity_meta(entity_type)['label']} not found: {slug}")


def list_entities(entity_type: str) -> list[dict[str, str]]:
    return [
        {"name": name, "slug": slugify_entity(name), "url": f"/{_entity_meta(entity_type)['plural']}/{slugify_entity(name)}"}
        for name in _all_entity_names(entity_type)
    ]


def _query_entity_rows(entity_type: str, name: str, hours: float, limit: int) -> list[tuple[GridSnapshot, Any]]:
    meta = _entity_meta(entity_type)
    model = meta["model"]
    name_col = getattr(model, meta["name_attr"])
    since = utc_now() - timedelta(hours=hours)

    base = (
        db.session.query(GridSnapshot, model)
        .join(model, model.snapshot_id == GridSnapshot.id)
        .filter(func.lower(name_col) == name.lower())
    )
    rows = (
        base.filter(GridSnapshot.reading_timestamp >= since)
        .order_by(GridSnapshot.reading_timestamp.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        rows = base.order_by(GridSnapshot.reading_timestamp.desc()).limit(limit).all()
    return list(reversed(rows))


def _history_payload(entity_type: str, rows: list[tuple[GridSnapshot, Any]]) -> list[dict[str, Any]]:
    meta = _entity_meta(entity_type)
    value_attr = meta["value_attr"]
    history = []
    for snapshot, entity_row in rows:
        value = getattr(entity_row, value_attr)
        total = (
            snapshot.total_load_allocation_mw
            if entity_type == "disco"
            else snapshot.total_generation_mw
        )
        share = (float(value) / float(total)) * 100 if value is not None and total else None
        history.append(
            {
                "timestamp": to_iso(snapshot.reading_timestamp),
                "captured_at": to_iso(snapshot.captured_at),
                "snapshot_id": snapshot.id,
                "value_mw": _round(float(value)) if value is not None else None,
                "share_percent": _round(share),
                "total_generation_mw": _round(float(snapshot.total_generation_mw)),
                "total_load_allocation_mw": _round(snapshot.total_load_allocation_mw),
            }
        )
    return history


def _trend(history: list[dict[str, Any]]) -> dict[str, Any]:
    points = [point for point in history if point["value_mw"] is not None]
    if len(points) < 2:
        return {"direction": "flat", "change_mw": 0, "change_percent": 0, "sample_count": len(points)}

    first = points[0]["value_mw"]
    latest = points[-1]["value_mw"]
    change = latest - first
    percent = (change / first) * 100 if first else None
    return {
        "from_timestamp": points[0]["timestamp"],
        "to_timestamp": points[-1]["timestamp"],
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
        "change_mw": _round(change),
        "change_percent": _round(percent),
        "sample_count": len(points),
    }


def _forecast(history: list[dict[str, Any]]) -> dict[str, Any]:
    points = [point for point in history if point["value_mw"] is not None]
    if len(points) < 2:
        latest = points[-1]["value_mw"] if points else None
        return {
            "method": "baseline_hold",
            "confidence": "low",
            "next_24h_mw": latest,
            "next_7d_mw": latest,
            "slope_mw_per_hour": 0,
        }

    first = points[0]
    latest = points[-1]
    start = parse_iso_datetime(first["timestamp"])
    end = parse_iso_datetime(latest["timestamp"])
    hours = max((end - start).total_seconds() / 3600 if start and end else len(points), 1)
    slope = (latest["value_mw"] - first["value_mw"]) / hours
    confidence = "high" if len(points) >= 48 else "medium" if len(points) >= 12 else "low"
    return {
        "method": "linear_recent_trend",
        "confidence": confidence,
        "next_24h_mw": _round(max(0, latest["value_mw"] + slope * 24)),
        "next_7d_mw": _round(max(0, latest["value_mw"] + slope * 168)),
        "slope_mw_per_hour": _round(slope, 3),
    }


def _stats(history: list[dict[str, Any]]) -> dict[str, Any]:
    values = [point["value_mw"] for point in history if point["value_mw"] is not None]
    if not values:
        return {
            "latest_mw": None,
            "average_mw": None,
            "highest_mw": None,
            "lowest_mw": None,
            "volatility_mw": None,
            "volatility_percent": None,
        }
    avg = mean(values)
    volatility = pstdev(values) if len(values) > 1 else 0
    return {
        "latest_mw": _round(values[-1]),
        "average_mw": _round(avg),
        "highest_mw": _round(max(values)),
        "lowest_mw": _round(min(values)),
        "volatility_mw": _round(volatility),
        "volatility_percent": _round((volatility / avg) * 100 if avg else 0),
    }


def _latest_rank(entity_type: str, name: str, latest: dict[str, Any] | None) -> dict[str, Any]:
    if not latest:
        return {"rank": None, "total_entities": 0, "value_mw": None}
    if entity_type == "disco":
        rows = (latest.get("disco_profile") or {}).get("discos") or []
        name_key = "company"
        value_key = "load_allocation_mw"
    else:
        rows = latest.get("gencos") or []
        name_key = "plant"
        value_key = "generation_mw"
    sorted_rows = sorted(rows, key=lambda row: float(row.get(value_key) or 0), reverse=True)
    for index, row in enumerate(sorted_rows, start=1):
        if row.get(name_key, "").lower() == name.lower():
            return {
                "rank": index,
                "total_entities": len(sorted_rows),
                "value_mw": _round(float(row.get(value_key) or 0)),
            }
    return {"rank": None, "total_entities": len(sorted_rows), "value_mw": None}


def _average_rank(entity_type: str, name: str) -> dict[str, Any]:
    meta = _entity_meta(entity_type)
    model = meta["model"]
    name_col = getattr(model, meta["name_attr"])
    value_col = getattr(model, meta["value_attr"])
    rows = db.session.query(name_col, func.avg(value_col)).group_by(name_col).all()
    rankings = sorted(
        [{"name": row[0], "average_mw": float(row[1] or 0)} for row in rows if row[0]],
        key=lambda row: row["average_mw"],
        reverse=True,
    )
    for index, row in enumerate(rankings, start=1):
        if row["name"].lower() == name.lower():
            return {"rank": index, "total_entities": len(rankings), "average_mw": _round(row["average_mw"])}
    return {"rank": None, "total_entities": len(rankings), "average_mw": None}


def _moving_average(history: list[dict[str, Any]], window: int = 6) -> list[dict[str, Any]]:
    values = []
    enriched = []
    for point in history:
        value = point["value_mw"]
        if value is not None:
            values.append(value)
        if len(values) > window:
            values.pop(0)
        enriched.append({**point, "moving_average_mw": _round(mean(values)) if values else None})
    return enriched


def _disco_distribution_context(name: str, latest: dict[str, Any] | None, hours: float) -> dict[str, Any] | None:
    if not latest:
        return None
    intelligence = distribution_intelligence(latest, get_history_points(hours, 336), hours)
    target_slug = slugify_entity(name)
    for row in intelligence.get("regional_risk") or []:
        if slugify_entity(row.get("company", "")) == target_slug:
            return {
                "classification": row.get("overload_warning"),
                "planning_region": row.get("planning_region"),
                "estimated_utilization_percent": row.get("estimated_utilization_percent"),
                "projected_utilization_12m_percent": row.get("projected_utilization_12m_percent"),
                "projected_utilization_36m_percent": row.get("projected_utilization_36m_percent"),
                "settlement_growth_percent": row.get("settlement_growth_percent"),
                "stress_index": row.get("settlement_growth_vs_stress"),
                "recommended_action": row.get("recommended_action"),
            }
    return None


def _risk(entity_type: str, stats: dict[str, Any], trend: dict[str, Any], distribution: dict[str, Any] | None) -> dict[str, Any]:
    if entity_type == "disco" and distribution:
        classification = distribution.get("classification") or "unknown"
        if classification == "overload_risk":
            severity = "critical"
        elif classification == "warning":
            severity = "elevated"
        elif classification == "watch":
            severity = "watch"
        else:
            severity = "normal"
        return {
            "classification": severity,
            "primary_driver": "transformer_utilization",
            "message": distribution.get("recommended_action") or "Monitor allocation and regional loading trend.",
        }

    volatility = stats.get("volatility_percent") or 0
    change = trend.get("change_percent") or 0
    if volatility >= 25 or change <= -30:
        classification = "elevated"
    elif volatility >= 12 or change <= -12:
        classification = "watch"
    else:
        classification = "normal"
    return {
        "classification": classification,
        "primary_driver": "output_volatility" if volatility >= 12 else "recent_trend",
        "message": (
            "Output is moving sharply and should be watched against the next readings."
            if classification != "normal"
            else "Recent performance is within the normal observed band."
        ),
    }


def _performance_score(stats: dict[str, Any], trend: dict[str, Any], rank: dict[str, Any]) -> dict[str, Any]:
    score = 70.0
    volatility = stats.get("volatility_percent") or 0
    change = trend.get("change_percent") or 0
    score -= min(25, volatility)
    score += max(-12, min(12, change / 2))
    if rank.get("rank") and rank.get("total_entities"):
        score += max(0, 15 * (1 - ((rank["rank"] - 1) / max(1, rank["total_entities"]))))
    score = max(0, min(100, score))
    if score >= 80:
        classification = "strong"
    elif score >= 60:
        classification = "stable"
    elif score >= 40:
        classification = "watch"
    else:
        classification = "weak"
    return {"score": _round(score, 1), "classification": classification}


def _analysis_summary(
    entity_type: str,
    name: str,
    stats: dict[str, Any],
    trend: dict[str, Any],
    forecast: dict[str, Any],
    risk: dict[str, Any],
    rank: dict[str, Any],
) -> str:
    label = _entity_meta(entity_type)["label"]
    rank_text = (
        f"ranked {rank['rank']} of {rank['total_entities']}"
        if rank.get("rank")
        else "not yet ranked"
    )
    latest = stats.get("latest_mw")
    average = stats.get("average_mw")
    direction = trend.get("direction", "flat")
    forecast_value = forecast.get("next_24h_mw")
    return (
        f"{name} is a {label} currently {rank_text} in the latest stored reading. "
        f"The latest value is {_round(latest) if latest is not None else 'unknown'} MW "
        f"against an observed average of {_round(average) if average is not None else 'unknown'} MW. "
        f"The recent trend is {direction}, with a {trend.get('change_mw', 0)} MW movement over the sampled window. "
        f"The short-term forecast points to {forecast_value if forecast_value is not None else 'insufficient data'} MW in 24 hours "
        f"with {forecast.get('confidence')} confidence. Risk is classified as {risk.get('classification')} because of "
        f"{risk.get('primary_driver')}. This is an automated analytical summary generated from public grid readings, "
        f"not operational dispatch advice."
    )


def entity_intelligence(entity_type: str, slug: str, hours: float = 168, limit: int = 1000) -> dict[str, Any]:
    meta = _entity_meta(entity_type)
    name = resolve_entity_name(entity_type, slug)
    rows = _query_entity_rows(entity_type, name, hours, limit)
    history = _moving_average(_history_payload(entity_type, rows))
    latest = get_latest_snapshot()
    stats = _stats(history)
    trend = _trend(history)
    forecast = _forecast(history)
    latest_rank = _latest_rank(entity_type, name, latest)
    average_rank = _average_rank(entity_type, name)
    distribution = _disco_distribution_context(name, latest, hours) if entity_type == "disco" else None
    risk = _risk(entity_type, stats, trend, distribution)
    performance = _performance_score(stats, trend, latest_rank)

    return {
        "entity": {
            "type": entity_type,
            "label": meta["label"],
            "name": name,
            "slug": slugify_entity(name),
            "unit": meta["unit"],
            "url": f"/{meta['plural']}/{slugify_entity(name)}",
        },
        "generated_at": utc_now_iso(),
        "window_hours": hours,
        "sample_count": len(history),
        "history": history,
        "statistics": stats,
        "trend": trend,
        "forecast": forecast,
        "risk": risk,
        "utilization": {
            "latest_share_percent": history[-1]["share_percent"] if history else None,
            "distribution": distribution,
        },
        "rankings": {
            "latest": latest_rank,
            "average": average_rank,
        },
        "performance": performance,
        "analysis_summary": _analysis_summary(
            entity_type,
            name,
            stats,
            trend,
            forecast,
            risk,
            latest_rank,
        ),
        "related": list_entities(entity_type),
    }
