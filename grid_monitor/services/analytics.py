from statistics import pstdev
from typing import Any

from flask import current_app

from grid_monitor.services.storage import get_latest_genco_snapshot
from grid_monitor.utils.time import to_iso


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def classify_grid_health(total_generation_mw: float | None) -> dict[str, Any]:
    if total_generation_mw is None:
        return {
            "classification": "unknown",
            "severity": "unknown",
            "message": "No generation reading available.",
        }

    critical = current_app.config["GRID_STRESS_CRITICAL_MW"]
    stressed = current_app.config["GRID_STRESS_STRESSED_MW"]
    stable = current_app.config["GRID_STRESS_STABLE_MW"]

    if total_generation_mw < critical:
        return {
            "classification": "critical",
            "severity": "red",
            "message": "Generation is below the critical operating band.",
        }
    if total_generation_mw < stressed:
        return {
            "classification": "stressed",
            "severity": "amber",
            "message": "Generation is below a stronger supply band.",
        }
    if total_generation_mw < stable:
        return {
            "classification": "stable",
            "severity": "green",
            "message": "Generation is within a stable operating band.",
        }
    return {
        "classification": "strong",
        "severity": "green",
        "message": "Generation is in a strong operating band.",
    }


def add_moving_average(points: list[dict[str, Any]], window_size: int | None = None) -> list[dict[str, Any]]:
    window_size = window_size or current_app.config["ROLLING_AVERAGE_WINDOW"]
    window: list[float] = []
    enriched: list[dict[str, Any]] = []
    for point in points:
        mw = float(point["total_generation_mw"])
        window.append(mw)
        if len(window) > window_size:
            window.pop(0)
        enriched.append({**point, "moving_average_mw": _round(sum(window) / len(window))})
    return enriched


def generation_trend(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not points:
        return None
    first = points[0]
    latest = points[-1]
    delta = latest["total_generation_mw"] - first["total_generation_mw"]
    percent_change = (
        (delta / first["total_generation_mw"]) * 100
        if first["total_generation_mw"]
        else None
    )
    return {
        "from_timestamp": first["timestamp"],
        "to_timestamp": latest["timestamp"],
        "change_mw": _round(delta),
        "change_percent": _round(percent_change),
        "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
    }


def peak_generation(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not points:
        return None
    peak = max(points, key=lambda item: item["total_generation_mw"])
    return {
        "timestamp": peak["timestamp"],
        "total_generation_mw": peak["total_generation_mw"],
    }


def generation_volatility(points: list[dict[str, Any]]) -> dict[str, Any]:
    if len(points) < 2:
        return {"volatility_mw": 0.0, "volatility_percent": 0.0, "classification": "insufficient_data"}
    values = [float(point["total_generation_mw"]) for point in points]
    average = sum(values) / len(values)
    volatility = pstdev(values)
    percent = (volatility / average) * 100 if average else 0.0
    if percent >= 15:
        classification = "high"
    elif percent >= 7:
        classification = "moderate"
    else:
        classification = "low"
    return {
        "volatility_mw": _round(volatility),
        "volatility_percent": _round(percent),
        "classification": classification,
    }


def detect_outages(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {
            "detected": False,
            "events": [],
            "event_count": 0,
            "classification": "unknown",
        }

    threshold_percent = current_app.config["OUTAGE_DROP_THRESHOLD_PERCENT"]
    critical_mw = current_app.config["OUTAGE_CRITICAL_MW"]
    events: list[dict[str, Any]] = []
    previous = None
    for point in points:
        mw = float(point["total_generation_mw"])
        if mw <= critical_mw:
            events.append(
                {
                    "timestamp": point["timestamp"],
                    "type": "critical_generation",
                    "generation_mw": _round(mw),
                    "threshold_mw": critical_mw,
                }
            )
        if previous:
            prev_mw = float(previous["total_generation_mw"])
            drop_percent = ((prev_mw - mw) / prev_mw) * 100 if prev_mw else 0
            if drop_percent >= threshold_percent:
                events.append(
                    {
                        "timestamp": point["timestamp"],
                        "type": "sharp_drop",
                        "from_generation_mw": _round(prev_mw),
                        "to_generation_mw": _round(mw),
                        "drop_percent": _round(drop_percent),
                    }
                )
        previous = point

    if not events:
        classification = "clear"
    elif len(events) <= 2:
        classification = "watch"
    else:
        classification = "elevated"
    return {
        "detected": bool(events),
        "events": events[-10:],
        "event_count": len(events),
        "classification": classification,
    }


def supply_stability_score(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {"score": None, "classification": "unknown"}
    volatility = generation_volatility(points)
    trend = generation_trend(points)
    volatility_penalty = min(45, (volatility["volatility_percent"] or 0) * 2.4)
    trend_penalty = min(20, abs((trend or {}).get("change_percent") or 0) * 0.8)
    sample_penalty = 15 if len(points) < 6 else 0
    score = max(0, min(100, 100 - volatility_penalty - trend_penalty - sample_penalty))
    if score >= 80:
        classification = "strong"
    elif score >= 60:
        classification = "fair"
    elif score >= 40:
        classification = "fragile"
    else:
        classification = "weak"
    return {"score": _round(score, 1), "classification": classification}


def rolling_health_score(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {"score": None, "classification": "unknown"}

    critical = current_app.config["GRID_STRESS_CRITICAL_MW"]
    stressed = current_app.config["GRID_STRESS_STRESSED_MW"]
    stable = current_app.config["GRID_STRESS_STABLE_MW"]
    scores: list[float] = []
    for point in points:
        mw = float(point["total_generation_mw"])
        if mw < critical:
            score = max(0, 35 * (mw / critical))
        elif mw < stressed:
            score = 35 + 25 * ((mw - critical) / max(1, stressed - critical))
        elif mw < stable:
            score = 60 + 25 * ((mw - stressed) / max(1, stable - stressed))
        else:
            score = min(100, 85 + 15 * min(1, (mw - stable) / max(1, stable)))
        scores.append(score)

    average = sum(scores) / len(scores)
    if average >= 80:
        classification = "healthy"
    elif average >= 60:
        classification = "stable"
    elif average >= 40:
        classification = "stressed"
    else:
        classification = "critical"
    return {"score": _round(average, 1), "classification": classification}


def disco_load_concentration(discos: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        row for row in discos
        if row.get("load_allocation_mw") is not None and row.get("company")
    ]
    total = sum(float(row["load_allocation_mw"]) for row in rows)
    if not rows or total <= 0:
        return {
            "total_load_allocation_mw": total or None,
            "top_company": None,
            "top_share_percent": None,
            "concentration_index": None,
            "classification": "unknown",
        }
    top = max(rows, key=lambda row: float(row["load_allocation_mw"]))
    shares = [float(row["load_allocation_mw"]) / total for row in rows]
    hhi = sum(share * share for share in shares)
    if hhi >= 0.2:
        classification = "concentrated"
    elif hhi >= 0.13:
        classification = "moderate"
    else:
        classification = "balanced"
    return {
        "total_load_allocation_mw": _round(total),
        "top_company": top["company"],
        "top_load_allocation_mw": _round(float(top["load_allocation_mw"])),
        "top_share_percent": _round((float(top["load_allocation_mw"]) / total) * 100),
        "concentration_index": _round(hhi, 4),
        "classification": classification,
    }


def top_performing_gencos(gencos: list[dict[str, Any]], total_generation_mw: float | None, limit: int = 5) -> list[dict[str, Any]]:
    rows = [
        row for row in gencos
        if row.get("generation_mw") is not None and row.get("plant")
    ]
    rows = sorted(rows, key=lambda row: float(row["generation_mw"]), reverse=True)
    return [
        {
            "plant": row["plant"],
            "generation_mw": _round(float(row["generation_mw"])),
            "share_percent": _round((float(row["generation_mw"]) / total_generation_mw) * 100)
            if total_generation_mw
            else None,
        }
        for row in rows[:limit]
    ]


def history_analytics(points: list[dict[str, Any]], hours: float, latest_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    points = add_moving_average(points)
    if not points:
        return {
            "window_hours": hours,
            "sample_count": 0,
            "last_24h_generation_trend": None,
            "rolling_average_mw": None,
            "moving_average_window_readings": current_app.config["ROLLING_AVERAGE_WINDOW"],
            "highest_daily_generation": None,
            "lowest_daily_generation": None,
            "peak_generation": None,
            "outage_detection": detect_outages(points),
            "generation_volatility": generation_volatility(points),
            "supply_stability_score": supply_stability_score(points),
            "rolling_health_score": rolling_health_score(points),
            "disco_load_concentration": disco_load_concentration([]),
            "top_performing_gencos": [],
            "grid_health": classify_grid_health(None),
        }

    highest = max(points, key=lambda item: item["total_generation_mw"])
    lowest = min(points, key=lambda item: item["total_generation_mw"])
    latest_snapshot = latest_snapshot or {}
    total_generation = latest_snapshot.get("total_generation_mw") or points[-1]["total_generation_mw"]
    latest_discos = (latest_snapshot.get("disco_profile") or {}).get("discos") or []
    latest_gencos = latest_snapshot.get("gencos") or []
    # The upstream GenCo table can go missing while generation still reports.
    # Fall back to the last stored reading that had one, carrying its own
    # timestamp so the UI can label it rather than imply it is current.
    genco_as_at = None
    if not latest_gencos:
        fallback = get_latest_genco_snapshot()
        if fallback is not None:
            latest_gencos = [
                {"plant": row.plant, "generation_mw": row.generation_mw}
                for row in fallback.genco_data
            ]
            genco_as_at = to_iso(fallback.reading_timestamp)

    return {
        "window_hours": hours,
        "sample_count": len(points),
        "last_24h_generation_trend": generation_trend(points),
        "rolling_average_mw": points[-1].get("moving_average_mw"),
        "moving_average_window_readings": current_app.config["ROLLING_AVERAGE_WINDOW"],
        "highest_daily_generation": {
            "timestamp": highest["timestamp"],
            "total_generation_mw": highest["total_generation_mw"],
        },
        "lowest_daily_generation": {
            "timestamp": lowest["timestamp"],
            "total_generation_mw": lowest["total_generation_mw"],
        },
        "peak_generation": peak_generation(points),
        "outage_detection": detect_outages(points),
        "generation_volatility": generation_volatility(points),
        "supply_stability_score": supply_stability_score(points),
        "rolling_health_score": rolling_health_score(points),
        "disco_load_concentration": disco_load_concentration(latest_discos),
        "top_performing_gencos": top_performing_gencos(latest_gencos, total_generation),
        "top_gencos_as_at": genco_as_at,
        "grid_health": classify_grid_health(total_generation),
    }


def enrich_history_payload(points: list[dict[str, Any]], hours: float, limit: int, latest_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    enriched_points = add_moving_average(points)
    return {
        "hours": hours,
        "limit": limit,
        "history": enriched_points,
        "analytics": history_analytics(enriched_points, hours, latest_snapshot),
    }


def multi_window_analytics(
    points_24h: list[dict[str, Any]],
    points_7d: list[dict[str, Any]],
    latest_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "trend_24h": history_analytics(points_24h, 24, latest_snapshot),
        "trend_7d": history_analytics(points_7d, 168, latest_snapshot),
    }
