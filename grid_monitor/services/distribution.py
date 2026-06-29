import re
from typing import Any

from flask import current_app

from grid_monitor.utils.time import utc_now_iso


DISCO_PROFILES = {
    "Abuja": {"region": "North Central / FCT", "growth": 4.2, "design_utilization": 0.82},
    "Benin": {"region": "South South", "growth": 3.4, "design_utilization": 0.8},
    "Eko": {"region": "Lagos Island / Coastal Lagos", "growth": 4.8, "design_utilization": 0.88},
    "Enugu": {"region": "South East", "growth": 3.2, "design_utilization": 0.78},
    "Ibadan": {"region": "South West", "growth": 4.0, "design_utilization": 0.82},
    "Ikeja": {"region": "Lagos Mainland / Industrial Lagos", "growth": 5.0, "design_utilization": 0.9},
    "Jos": {"region": "North Central", "growth": 2.8, "design_utilization": 0.76},
    "Kaduna": {"region": "North West", "growth": 3.5, "design_utilization": 0.8},
    "Kano": {"region": "North West / Kano", "growth": 4.4, "design_utilization": 0.84},
    "Port Harcourt": {"region": "Rivers / South South", "growth": 4.3, "design_utilization": 0.85},
    "Yola": {"region": "North East", "growth": 2.9, "design_utilization": 0.74},
}


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _slugify_entity(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return cleaned.strip("-") or "unknown"


def _capacity_margin(utilization_percent: float | None, overload_threshold: float) -> float | None:
    if utilization_percent is None:
        return None
    return _round(overload_threshold - utilization_percent)


def _profile_for(company: str) -> dict[str, Any]:
    cleaned = company.replace("DisCo", "").replace("DISCO", "").strip()
    for key, profile in DISCO_PROFILES.items():
        if key.lower() in cleaned.lower():
            return profile
    return {
        "region": cleaned or company,
        "growth": current_app.config["SETTLEMENT_GROWTH_BASE_PERCENT"],
        "design_utilization": current_app.config["TRANSFORMER_BASE_UTILIZATION"],
    }


def _risk_classification(current_utilization: float, projected_12m: float) -> str:
    warning = current_app.config["TRANSFORMER_WARNING_UTILIZATION_PERCENT"]
    overload = current_app.config["TRANSFORMER_OVERLOAD_UTILIZATION_PERCENT"]
    if current_utilization >= overload or projected_12m >= 100:
        return "overload_risk"
    if current_utilization >= warning or projected_12m >= overload:
        return "warning"
    if current_utilization >= warning - 10 or projected_12m >= warning:
        return "watch"
    return "normal"


def _recommended_action(classification: str) -> str:
    if classification == "overload_risk":
        return "Prioritize feeder relief, transformer augmentation, and load transfer planning."
    if classification == "warning":
        return "Review N-1 capacity, near-term settlement growth, and distribution reinforcement options."
    if classification == "watch":
        return "Track evening peak growth and update local transformer loading assumptions."
    return "Monitor normal loading and refresh planning assumptions as new readings arrive."


def _portfolio_classification(regions: list[dict[str, Any]]) -> str:
    if not regions:
        return "unknown"
    critical = sum(1 for item in regions if item["overload_warning"] == "overload_risk")
    warning = sum(1 for item in regions if item["overload_warning"] == "warning")
    watch = sum(1 for item in regions if item["overload_warning"] == "watch")
    if critical:
        return "critical"
    if warning >= 3 or warning / len(regions) >= 0.25:
        return "elevated"
    if warning or watch >= 3:
        return "watch"
    return "normal"


def _weighted_average(rows: list[dict[str, Any]], value_key: str, weight_key: str = "load_allocation_mw") -> float | None:
    total_weight = sum((row.get(weight_key) or 0) for row in rows)
    if not total_weight:
        return None
    return sum((row.get(value_key) or 0) * (row.get(weight_key) or 0) for row in rows) / total_weight


def _disco_transformer_trend(
    item: dict[str, Any],
    history_points: list[dict[str, Any]],
    latest_generation: float,
    latest_snapshot: dict[str, Any] | None,
    warning: float,
    overload: float,
) -> list[dict[str, Any]]:
    current_utilization = item.get("estimated_utilization_percent") or 0
    projected_12m = item.get("projected_utilization_12m_percent") or 0
    projected_36m = item.get("projected_utilization_36m_percent") or 0
    trend = []

    for point in history_points:
        generation = float(point.get("total_generation_mw") or 0)
        scale = generation / latest_generation if latest_generation else 1
        scaled_current = min(160, current_utilization * scale)
        scaled_projected = min(180, projected_12m * scale)
        trend.append(
            {
                "timestamp": point.get("timestamp"),
                "label": point.get("timestamp"),
                "estimated_utilization_percent": _round(scaled_current),
                "weighted_utilization_percent": _round(scaled_current),
                "projected_utilization_12m_percent": _round(scaled_projected),
                "capacity_margin_percent": _capacity_margin(scaled_current, overload),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            }
        )

    if len(trend) < 2:
        trend = [
            {
                "label": "Current",
                "timestamp": (latest_snapshot or {}).get("reading_timestamp"),
                "estimated_utilization_percent": _round(current_utilization),
                "weighted_utilization_percent": _round(current_utilization),
                "projected_utilization_12m_percent": _round(projected_12m),
                "capacity_margin_percent": _capacity_margin(current_utilization, overload),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            },
            {
                "label": "12 months",
                "timestamp": None,
                "estimated_utilization_percent": _round(projected_12m),
                "weighted_utilization_percent": _round(projected_12m),
                "projected_utilization_12m_percent": _round(projected_12m),
                "capacity_margin_percent": _capacity_margin(projected_12m, overload),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            },
            {
                "label": "36 months",
                "timestamp": None,
                "estimated_utilization_percent": _round(projected_36m),
                "weighted_utilization_percent": _round(projected_36m),
                "projected_utilization_12m_percent": _round(projected_12m),
                "capacity_margin_percent": _capacity_margin(projected_36m, overload),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            },
        ]

    return trend


def _disco_settlement_trend(item: dict[str, Any], latest_snapshot: dict[str, Any] | None, overload: float) -> list[dict[str, Any]]:
    load_mw = item.get("load_allocation_mw") or 0
    growth_percent = item.get("settlement_growth_percent") or 0
    stress = item.get("settlement_growth_vs_stress") or 0
    projected_12m = item.get("projected_utilization_12m_percent") or 0
    projected_36m = item.get("projected_utilization_36m_percent") or 0
    growth_12m = load_mw * (growth_percent / 100)
    growth_36m = load_mw * (((1 + (growth_percent / 100)) ** 3) - 1)
    return [
        {
            "label": "Current",
            "timestamp": (latest_snapshot or {}).get("reading_timestamp"),
            "projected_load_growth_mw": 0,
            "settlement_stress_index": _round(stress),
            "regions_projected_overload": 0,
            "capacity_margin_percent": item.get("capacity_margin_percent"),
        },
        {
            "label": "12 months",
            "timestamp": None,
            "projected_load_growth_mw": _round(growth_12m),
            "settlement_stress_index": _round(min(100, stress * 1.08)),
            "regions_projected_overload": 1 if projected_12m >= overload else 0,
            "capacity_margin_percent": item.get("projected_capacity_margin_12m_percent"),
        },
        {
            "label": "36 months",
            "timestamp": None,
            "projected_load_growth_mw": _round(growth_36m),
            "settlement_stress_index": _round(min(100, stress * 1.18)),
            "regions_projected_overload": 1 if projected_36m >= overload else 0,
            "capacity_margin_percent": _capacity_margin(projected_36m, overload),
        },
    ]


def distribution_intelligence(
    latest_snapshot: dict[str, Any] | None,
    history_points: list[dict[str, Any]],
    hours: float,
) -> dict[str, Any]:
    profile = (latest_snapshot or {}).get("disco_profile") or {}
    discos = profile.get("discos") or []
    power_factor = max(0.1, min(1.0, current_app.config["DISTRIBUTION_POWER_FACTOR"]))
    warning = current_app.config["TRANSFORMER_WARNING_UTILIZATION_PERCENT"]
    overload = current_app.config["TRANSFORMER_OVERLOAD_UTILIZATION_PERCENT"]
    latest_generation = (latest_snapshot or {}).get("total_generation_mw") or 0

    rows = [
        row for row in discos
        if row.get("company") and row.get("load_allocation_mw") is not None
    ]
    total_load = sum(float(row["load_allocation_mw"]) for row in rows)
    regional_risk: list[dict[str, Any]] = []

    for row in rows:
        company = row["company"]
        load_mw = max(0.0, float(row["load_allocation_mw"]))
        disco_profile = _profile_for(company)
        design_utilization = max(
            0.45,
            min(0.95, float(disco_profile["design_utilization"])),
        )
        growth_percent = float(disco_profile["growth"])
        load_mva = load_mw / power_factor
        transformer_capacity_mva = load_mva / design_utilization if load_mva else 0
        utilization = (load_mva / transformer_capacity_mva) * 100 if transformer_capacity_mva else 0
        projected_12m = utilization * (1 + growth_percent / 100)
        projected_36m = utilization * ((1 + growth_percent / 100) ** 3)
        stress_index = min(
            100.0,
            (utilization * 0.58) + (projected_12m * 0.27) + (growth_percent * 2.4),
        )
        classification = _risk_classification(utilization, projected_12m)
        regional_risk.append(
            {
                "company": company,
                "slug": _slugify_entity(company),
                "planning_region": disco_profile["region"],
                "load_allocation_mw": _round(load_mw),
                "load_share_percent": _round((load_mw / total_load) * 100 if total_load else None),
                "estimated_transformer_capacity_mva": _round(transformer_capacity_mva),
                "current_utilization_percent": _round(utilization),
                "estimated_utilization_percent": _round(utilization),
                "projected_utilization_12m_percent": _round(projected_12m),
                "projected_utilization_36m_percent": _round(projected_36m),
                "capacity_margin_percent": _capacity_margin(utilization, overload),
                "projected_capacity_margin_12m_percent": _capacity_margin(projected_12m, overload),
                "settlement_growth_percent": _round(growth_percent, 1),
                "settlement_growth_vs_stress": _round(stress_index, 1),
                "overload_warning": classification,
                "recommended_action": _recommended_action(classification),
            }
        )

    regional_risk.sort(
        key=lambda item: (
            item["settlement_growth_vs_stress"] or 0,
            item["estimated_utilization_percent"] or 0,
        ),
        reverse=True,
    )

    weighted_utilization = (
        sum(
            (item["estimated_utilization_percent"] or 0)
            * (item["load_allocation_mw"] or 0)
            for item in regional_risk
        )
        / total_load
        if total_load
        else None
    )
    projected_growth_mw_12m = sum(
        (item["load_allocation_mw"] or 0) * ((item["settlement_growth_percent"] or 0) / 100)
        for item in regional_risk
    )
    projected_growth_mw_36m = sum(
        (item["load_allocation_mw"] or 0)
        * (((1 + ((item["settlement_growth_percent"] or 0) / 100)) ** 3) - 1)
        for item in regional_risk
    )
    portfolio = _portfolio_classification(regional_risk)
    projected_utilization_12m = _weighted_average(regional_risk, "projected_utilization_12m_percent") or 0
    projected_utilization_36m = _weighted_average(regional_risk, "projected_utilization_36m_percent") or 0
    weighted_stress = _weighted_average(regional_risk, "settlement_growth_vs_stress") or 0
    portfolio_capacity_margin = _capacity_margin(weighted_utilization, overload)
    portfolio_projected_capacity_margin_12m = _capacity_margin(projected_utilization_12m, overload)

    trend = []
    base_weighted = weighted_utilization or 0
    for point in history_points:
        generation = float(point.get("total_generation_mw") or 0)
        scale = generation / latest_generation if latest_generation else 1
        trend.append(
            {
                "timestamp": point.get("timestamp"),
                "label": point.get("timestamp"),
                "weighted_utilization_percent": _round(min(160, base_weighted * scale)),
                "projected_utilization_12m_percent": _round(min(180, projected_utilization_12m * scale)),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            }
        )
    if len(trend) < 2 and regional_risk:
        trend = [
            {
                "label": "Current",
                "timestamp": (latest_snapshot or {}).get("reading_timestamp"),
                "weighted_utilization_percent": _round(base_weighted),
                "projected_utilization_12m_percent": _round(projected_utilization_12m),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            },
            {
                "label": "12 months",
                "timestamp": None,
                "weighted_utilization_percent": _round(projected_utilization_12m),
                "projected_utilization_12m_percent": _round(projected_utilization_12m),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            },
            {
                "label": "36 months",
                "timestamp": None,
                "weighted_utilization_percent": _round(projected_utilization_36m),
                "projected_utilization_12m_percent": _round(projected_utilization_12m),
                "warning_threshold_percent": warning,
                "overload_threshold_percent": overload,
            },
        ]

    settlement_trend = [
        {
            "label": "Current",
            "timestamp": (latest_snapshot or {}).get("reading_timestamp"),
            "projected_load_growth_mw": 0,
            "settlement_stress_index": _round(weighted_stress),
            "regions_projected_overload": 0,
        },
        {
            "label": "12 months",
            "timestamp": None,
            "projected_load_growth_mw": _round(projected_growth_mw_12m),
            "settlement_stress_index": _round(min(100, weighted_stress * 1.08)),
            "regions_projected_overload": sum(
                1 for item in regional_risk
                if (item["projected_utilization_12m_percent"] or 0) >= overload
            ),
        },
        {
            "label": "36 months",
            "timestamp": None,
            "projected_load_growth_mw": _round(projected_growth_mw_36m),
            "settlement_stress_index": _round(min(100, weighted_stress * 1.18)),
            "regions_projected_overload": sum(
                1 for item in regional_risk
                if (item["projected_utilization_36m_percent"] or 0) >= overload
            ),
        },
    ] if regional_risk else []

    disco_drilldowns = {
        item["slug"]: {
            "company": item["company"],
            "slug": item["slug"],
            "planning_region": item.get("planning_region"),
            "load_allocation_mw": item.get("load_allocation_mw"),
            "load_share_percent": item.get("load_share_percent"),
            "current_utilization_percent": item.get("estimated_utilization_percent"),
            "estimated_utilization_percent": item.get("estimated_utilization_percent"),
            "projected_utilization_12m_percent": item.get("projected_utilization_12m_percent"),
            "projected_utilization_36m_percent": item.get("projected_utilization_36m_percent"),
            "capacity_margin_percent": item.get("capacity_margin_percent"),
            "projected_capacity_margin_12m_percent": item.get("projected_capacity_margin_12m_percent"),
            "settlement_growth_percent": item.get("settlement_growth_percent"),
            "settlement_growth_vs_stress": item.get("settlement_growth_vs_stress"),
            "overload_warning": item.get("overload_warning"),
            "recommended_action": item.get("recommended_action"),
            "transformer_loading_trend": _disco_transformer_trend(
                item,
                history_points,
                latest_generation,
                latest_snapshot,
                warning,
                overload,
            ),
            "settlement_expansion_trend": _disco_settlement_trend(item, latest_snapshot, overload),
            "detail_url": f"/discos/{item['slug']}",
        }
        for item in regional_risk
    }

    return {
        "window_hours": hours,
        "generated_at": utc_now_iso(),
        "methodology": {
            "basis": "DisCo load allocation is used as a proxy for regional distribution loading.",
            "power_factor": power_factor,
            "warning_threshold_percent": warning,
            "overload_threshold_percent": overload,
            "model_type": "planning estimate, not a SCADA transformer telemetry reading",
        },
        "summary": {
            "region_count": len(regional_risk),
            "total_load_allocation_mw": _round(total_load),
            "weighted_utilization_percent": _round(weighted_utilization),
            "projected_utilization_12m_percent": _round(projected_utilization_12m),
            "projected_utilization_36m_percent": _round(projected_utilization_36m),
            "capacity_margin_percent": portfolio_capacity_margin,
            "projected_capacity_margin_12m_percent": portfolio_projected_capacity_margin_12m,
            "weighted_settlement_stress_index": _round(weighted_stress),
            "overload_warning_classification": portfolio,
            "regions_at_warning_or_higher": sum(
                1 for item in regional_risk
                if item["overload_warning"] in {"warning", "overload_risk"}
            ),
            "highest_risk_region": regional_risk[0] if regional_risk else None,
        },
        "transformer_utilization": {
            "weighted_utilization_percent": _round(weighted_utilization),
            "projected_utilization_12m_percent": _round(projected_utilization_12m),
            "projected_utilization_36m_percent": _round(projected_utilization_36m),
            "capacity_margin_percent": portfolio_capacity_margin,
            "projected_capacity_margin_12m_percent": portfolio_projected_capacity_margin_12m,
            "warning_threshold_percent": warning,
            "overload_threshold_percent": overload,
            "classification": portfolio,
        },
        "overloaded_transformer_risk": regional_risk[:5],
        "regional_risk": regional_risk,
        "disco_drilldowns": disco_drilldowns,
        "transformer_loading_trend": trend,
        "settlement_expansion_trend": settlement_trend,
        "settlement_expansion_impact": {
            "projected_load_growth_12m_mw": _round(projected_growth_mw_12m),
            "projected_load_growth_36m_mw": _round(projected_growth_mw_36m),
            "regions_projected_overload_12m": sum(
                1 for item in regional_risk
                if (item["projected_utilization_12m_percent"] or 0) >= overload
            ),
            "regions_projected_overload_36m": sum(
                1 for item in regional_risk
                if (item["projected_utilization_36m_percent"] or 0) >= overload
            ),
            "planning_signal": (
                "reinforcement_required"
                if portfolio in {"critical", "elevated"}
                else "monitor_growth"
                if portfolio == "watch"
                else "normal_monitoring"
            ),
        },
    }
