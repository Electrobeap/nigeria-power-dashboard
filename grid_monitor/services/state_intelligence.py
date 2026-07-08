import math
from datetime import timedelta
from statistics import mean, pstdev
from typing import Any

from grid_monitor.extensions import db
from grid_monitor.models import GridSnapshot
from grid_monitor.services.entity_intelligence import slugify_entity
from grid_monitor.utils.time import parse_iso_datetime, to_iso, utc_now, utc_now_iso
from sqlalchemy.orm import selectinload


DISCO_LABELS = {
    "abuja": "Abuja DisCo",
    "benin": "Benin DisCo",
    "eko": "Eko DisCo",
    "enugu": "Enugu DisCo",
    "ibadan": "Ibadan DisCo",
    "ikeja": "Ikeja DisCo",
    "jos": "Jos DisCo",
    "kaduna": "Kaduna DisCo",
    "kano": "Kano DisCo",
    "port_harcourt": "Port Harcourt DisCo",
    "yola": "Yola DisCo",
}


REGION_LABELS = {
    "north-central": "North Central",
    "north-east": "North East",
    "north-west": "North West",
    "south-east": "South East",
    "south-south": "South South",
    "south-west": "South West",
}


STATE_PROFILES: dict[str, dict[str, Any]] = {
    "abia": {"name": "Abia", "region": "south-east", "population_m": 4.1, "growth": 3.0, "settlement": 58, "urban": 0.58, "industrial": 0.62, "discos": {"enugu": 0.20}},
    "adamawa": {"name": "Adamawa", "region": "north-east", "population_m": 4.9, "growth": 2.8, "settlement": 42, "urban": 0.34, "industrial": 0.25, "discos": {"yola": 0.30}},
    "akwa-ibom": {"name": "Akwa Ibom", "region": "south-south", "population_m": 5.8, "growth": 3.2, "settlement": 61, "urban": 0.54, "industrial": 0.55, "discos": {"port_harcourt": 0.27}},
    "anambra": {"name": "Anambra", "region": "south-east", "population_m": 6.0, "growth": 3.1, "settlement": 70, "urban": 0.66, "industrial": 0.72, "discos": {"enugu": 0.24}},
    "bauchi": {"name": "Bauchi", "region": "north-east", "population_m": 7.5, "growth": 3.3, "settlement": 52, "urban": 0.36, "industrial": 0.28, "discos": {"jos": 0.25}},
    "bayelsa": {"name": "Bayelsa", "region": "south-south", "population_m": 2.6, "growth": 3.0, "settlement": 50, "urban": 0.48, "industrial": 0.45, "discos": {"port_harcourt": 0.19}},
    "benue": {"name": "Benue", "region": "north-central", "population_m": 6.4, "growth": 3.0, "settlement": 48, "urban": 0.37, "industrial": 0.32, "discos": {"jos": 0.24}},
    "borno": {"name": "Borno", "region": "north-east", "population_m": 6.5, "growth": 2.9, "settlement": 46, "urban": 0.40, "industrial": 0.24, "discos": {"yola": 0.27}},
    "cross-river": {"name": "Cross River", "region": "south-south", "population_m": 4.4, "growth": 3.0, "settlement": 54, "urban": 0.43, "industrial": 0.38, "discos": {"port_harcourt": 0.22}},
    "delta": {"name": "Delta", "region": "south-south", "population_m": 5.8, "growth": 3.1, "settlement": 66, "urban": 0.60, "industrial": 0.72, "discos": {"benin": 0.30}},
    "ebonyi": {"name": "Ebonyi", "region": "south-east", "population_m": 3.2, "growth": 2.9, "settlement": 44, "urban": 0.34, "industrial": 0.28, "discos": {"enugu": 0.14}},
    "edo": {"name": "Edo", "region": "south-south", "population_m": 4.8, "growth": 3.0, "settlement": 62, "urban": 0.60, "industrial": 0.63, "discos": {"benin": 0.27}},
    "ekiti": {"name": "Ekiti", "region": "south-west", "population_m": 3.6, "growth": 2.8, "settlement": 42, "urban": 0.44, "industrial": 0.30, "discos": {"benin": 0.18, "ibadan": 0.04}},
    "enugu": {"name": "Enugu", "region": "south-east", "population_m": 4.8, "growth": 3.0, "settlement": 60, "urban": 0.60, "industrial": 0.58, "discos": {"enugu": 0.21}},
    "fct": {"name": "Federal Capital Territory", "short_name": "FCT", "region": "north-central", "population_m": 4.5, "growth": 4.2, "settlement": 78, "urban": 0.86, "industrial": 0.70, "discos": {"abuja": 0.40}},
    "gombe": {"name": "Gombe", "region": "north-east", "population_m": 3.8, "growth": 3.1, "settlement": 45, "urban": 0.38, "industrial": 0.26, "discos": {"jos": 0.22}},
    "imo": {"name": "Imo", "region": "south-east", "population_m": 5.6, "growth": 3.1, "settlement": 64, "urban": 0.58, "industrial": 0.56, "discos": {"enugu": 0.21}},
    "jigawa": {"name": "Jigawa", "region": "north-west", "population_m": 6.8, "growth": 3.2, "settlement": 42, "urban": 0.30, "industrial": 0.20, "discos": {"kano": 0.25}},
    "kaduna": {"name": "Kaduna", "region": "north-west", "population_m": 9.2, "growth": 3.3, "settlement": 65, "urban": 0.58, "industrial": 0.68, "discos": {"kaduna": 0.38}},
    "kano": {"name": "Kano", "region": "north-west", "population_m": 15.5, "growth": 3.5, "settlement": 78, "urban": 0.64, "industrial": 0.72, "discos": {"kano": 0.50}},
    "katsina": {"name": "Katsina", "region": "north-west", "population_m": 8.5, "growth": 3.2, "settlement": 48, "urban": 0.36, "industrial": 0.26, "discos": {"kano": 0.25}},
    "kebbi": {"name": "Kebbi", "region": "north-west", "population_m": 5.0, "growth": 3.0, "settlement": 40, "urban": 0.31, "industrial": 0.22, "discos": {"kaduna": 0.19}},
    "kogi": {"name": "Kogi", "region": "north-central", "population_m": 4.8, "growth": 3.0, "settlement": 48, "urban": 0.42, "industrial": 0.42, "discos": {"abuja": 0.19, "ibadan": 0.02}},
    "kwara": {"name": "Kwara", "region": "north-central", "population_m": 3.7, "growth": 2.8, "settlement": 46, "urban": 0.48, "industrial": 0.38, "discos": {"ibadan": 0.15}},
    "lagos": {"name": "Lagos", "region": "south-west", "population_m": 16.5, "growth": 3.7, "settlement": 92, "urban": 0.96, "industrial": 0.95, "discos": {"eko": 1.0, "ikeja": 1.0}},
    "nasarawa": {"name": "Nasarawa", "region": "north-central", "population_m": 3.2, "growth": 3.1, "settlement": 50, "urban": 0.38, "industrial": 0.28, "discos": {"abuja": 0.18}},
    "niger": {"name": "Niger", "region": "north-central", "population_m": 6.5, "growth": 3.2, "settlement": 45, "urban": 0.35, "industrial": 0.30, "discos": {"abuja": 0.23, "ibadan": 0.02}},
    "ogun": {"name": "Ogun", "region": "south-west", "population_m": 6.0, "growth": 3.4, "settlement": 72, "urban": 0.62, "industrial": 0.80, "discos": {"ibadan": 0.28}},
    "ondo": {"name": "Ondo", "region": "south-west", "population_m": 5.0, "growth": 3.0, "settlement": 55, "urban": 0.50, "industrial": 0.48, "discos": {"benin": 0.25}},
    "osun": {"name": "Osun", "region": "south-west", "population_m": 4.7, "growth": 2.9, "settlement": 52, "urban": 0.50, "industrial": 0.40, "discos": {"ibadan": 0.18}},
    "oyo": {"name": "Oyo", "region": "south-west", "population_m": 8.0, "growth": 3.2, "settlement": 70, "urban": 0.62, "industrial": 0.58, "discos": {"ibadan": 0.31}},
    "plateau": {"name": "Plateau", "region": "north-central", "population_m": 4.7, "growth": 2.9, "settlement": 50, "urban": 0.46, "industrial": 0.36, "discos": {"jos": 0.29}},
    "rivers": {"name": "Rivers", "region": "south-south", "population_m": 7.2, "growth": 3.4, "settlement": 78, "urban": 0.72, "industrial": 0.88, "discos": {"port_harcourt": 0.32}},
    "sokoto": {"name": "Sokoto", "region": "north-west", "population_m": 6.0, "growth": 3.1, "settlement": 44, "urban": 0.36, "industrial": 0.26, "discos": {"kaduna": 0.20}},
    "taraba": {"name": "Taraba", "region": "north-east", "population_m": 3.6, "growth": 2.9, "settlement": 38, "urban": 0.28, "industrial": 0.20, "discos": {"yola": 0.22}},
    "yobe": {"name": "Yobe", "region": "north-east", "population_m": 4.1, "growth": 3.0, "settlement": 36, "urban": 0.30, "industrial": 0.18, "discos": {"yola": 0.21}},
    "zamfara": {"name": "Zamfara", "region": "north-west", "population_m": 5.8, "growth": 3.1, "settlement": 42, "urban": 0.30, "industrial": 0.20, "discos": {"kaduna": 0.23}},
}


class GeographyNotFound(ValueError):
    pass


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _disco_key(value: str | None) -> str | None:
    cleaned = slugify_entity(value or "")
    if "port" in cleaned and "harcourt" in cleaned:
        return "port_harcourt"
    for key in DISCO_LABELS:
        if key.replace("_", "-") in cleaned:
            return key
    return None


def _profile_display(profile: dict[str, Any]) -> str:
    return profile.get("short_name") or profile["name"]


def _responsible_discos(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": DISCO_LABELS[key], "share_of_disco_percent": _round(share * 100, 1)}
        for key, share in profile["discos"].items()
    ]


def _snapshot_allocations(snapshot: GridSnapshot) -> dict[str, float]:
    allocations: dict[str, float] = {}
    for row in snapshot.disco_data:
        key = _disco_key(row.company)
        if key and row.load_allocation_mw is not None:
            allocations[key] = allocations.get(key, 0.0) + float(row.load_allocation_mw)
    return allocations


def _estimate_allocation(profile: dict[str, Any], allocations: dict[str, float]) -> tuple[float | None, list[dict[str, Any]]]:
    total = 0.0
    components = []
    for key, share in profile["discos"].items():
        disco_allocation = allocations.get(key)
        if disco_allocation is None:
            continue
        contribution = disco_allocation * share
        total += contribution
        components.append(
            {
                "disco": DISCO_LABELS[key],
                "share_of_disco_percent": _round(share * 100, 1),
                "estimated_allocation_mw": _round(contribution),
            }
        )
    return (total if components else None), components


def _state_estimated_peak(profile: dict[str, Any]) -> float:
    demand_per_million = 45 + (75 * profile["urban"]) + (35 * profile["industrial"])
    return profile["population_m"] * demand_per_million


def _metrics(profile: dict[str, Any], latest_allocation: float | None) -> dict[str, Any]:
    peak_demand = _state_estimated_peak(profile)
    availability = (latest_allocation / peak_demand) * 100 if latest_allocation is not None and peak_demand else None
    availability_capped = min(100, availability) if availability is not None else None
    stress = (
        min(
            100,
            max(
                0,
                100
                - ((availability_capped or 0) * 0.55)
                + (profile["settlement"] * 0.18)
                + (profile["growth"] * 4.2)
                + (profile["industrial"] * 12),
            ),
        )
        if availability is not None
        else None
    )
    transformer = (
        min(100, max(0, (stress or 0) * 0.62 + profile["settlement"] * 0.25 + profile["growth"] * 4.0))
        if stress is not None
        else None
    )
    reliability = (
        min(100, max(0, (availability_capped or 0) * 0.62 + (100 - (transformer or 0)) * 0.38))
        if availability is not None
        else None
    )
    served = profile["population_m"] * min(0.92, max(0.35, 0.32 + (availability_capped or 0) / 145))
    return {
        "estimated_peak_demand_mw": _round(peak_demand),
        "estimated_demand_growth_percent": profile["growth"],
        "population_served_estimate_m": _round(served, 2),
        "settlement_growth_indicator": _round(profile["settlement"], 1),
        "infrastructure_stress_score": _round(stress, 1),
        "transformer_risk_score": _round(transformer, 1),
        "grid_reliability_score": _round(reliability, 1),
        "power_availability_estimate_percent": _round(availability_capped, 1),
    }


def _trend(history: list[dict[str, Any]]) -> dict[str, Any]:
    points = [item for item in history if item["estimated_allocation_mw"] is not None]
    if len(points) < 2:
        return {"direction": "flat", "change_mw": 0, "change_percent": 0, "sample_count": len(points)}
    first = points[0]["estimated_allocation_mw"]
    latest = points[-1]["estimated_allocation_mw"]
    change = latest - first
    return {
        "from_timestamp": points[0]["timestamp"],
        "to_timestamp": points[-1]["timestamp"],
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
        "change_mw": _round(change),
        "change_percent": _round((change / first) * 100 if first else None),
        "sample_count": len(points),
    }


def _stats(history: list[dict[str, Any]]) -> dict[str, Any]:
    values = [item["estimated_allocation_mw"] for item in history if item["estimated_allocation_mw"] is not None]
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


def _forecast(history: list[dict[str, Any]]) -> dict[str, Any]:
    points = [item for item in history if item["estimated_allocation_mw"] is not None]
    if len(points) < 2:
        latest = points[-1]["estimated_allocation_mw"] if points else None
        return {"method": "baseline_hold", "confidence": "low", "next_24h_mw": latest, "next_7d_mw": latest}
    start = parse_iso_datetime(points[0]["timestamp"])
    end = parse_iso_datetime(points[-1]["timestamp"])
    hours = max((end - start).total_seconds() / 3600 if start and end else len(points), 1)
    slope = (points[-1]["estimated_allocation_mw"] - points[0]["estimated_allocation_mw"]) / hours
    confidence = "high" if len(points) >= 48 else "medium" if len(points) >= 12 else "low"
    return {
        "method": "linear_recent_trend",
        "confidence": confidence,
        "next_24h_mw": _round(max(0, points[-1]["estimated_allocation_mw"] + slope * 24)),
        "next_7d_mw": _round(max(0, points[-1]["estimated_allocation_mw"] + slope * 168)),
        "slope_mw_per_hour": _round(slope, 3),
    }


def _moving_average(history: list[dict[str, Any]], window_size: int = 6) -> list[dict[str, Any]]:
    window = []
    enriched = []
    for point in history:
        value = point["estimated_allocation_mw"]
        if value is not None:
            window.append(value)
        if len(window) > window_size:
            window.pop(0)
        enriched.append({**point, "moving_average_mw": _round(mean(window)) if window else None})
    return enriched


def _snapshot_rows(hours: float, limit: int) -> list[GridSnapshot]:
    since = utc_now() - timedelta(hours=hours)
    rows = (
        GridSnapshot.query.options(selectinload(GridSnapshot.disco_data))
        .filter(GridSnapshot.reading_timestamp >= since)
        .order_by(GridSnapshot.reading_timestamp.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        rows = (
            GridSnapshot.query.options(selectinload(GridSnapshot.disco_data))
            .order_by(GridSnapshot.reading_timestamp.desc())
            .limit(limit)
            .all()
        )
    return list(reversed(rows))


def _history_for_profile(profile: dict[str, Any], hours: float, limit: int) -> list[dict[str, Any]]:
    history = []
    for snapshot in _snapshot_rows(hours, limit):
        allocation, components = _estimate_allocation(profile, _snapshot_allocations(snapshot))
        metrics = _metrics(profile, allocation)
        history.append(
            {
                "timestamp": to_iso(snapshot.reading_timestamp),
                "captured_at": to_iso(snapshot.captured_at),
                "estimated_allocation_mw": _round(allocation),
                "estimated_peak_demand_mw": metrics["estimated_peak_demand_mw"],
                "power_availability_estimate_percent": metrics["power_availability_estimate_percent"],
                "grid_reliability_score": metrics["grid_reliability_score"],
                "infrastructure_stress_score": metrics["infrastructure_stress_score"],
                "components": components,
            }
        )
    return _moving_average(history)


def _rankings(target_slug: str, latest_snapshot: GridSnapshot | None) -> dict[str, Any]:
    if not latest_snapshot:
        return {"allocation_rank": None, "stress_rank": None, "reliability_rank": None, "peer_count": len(STATE_PROFILES)}
    allocations = _snapshot_allocations(latest_snapshot)
    rows = []
    for slug, profile in STATE_PROFILES.items():
        allocation, _ = _estimate_allocation(profile, allocations)
        metrics = _metrics(profile, allocation)
        rows.append(
            {
                "slug": slug,
                "name": profile["name"],
                "allocation": allocation or 0,
                "stress": metrics["infrastructure_stress_score"] if metrics["infrastructure_stress_score"] is not None else 101,
                "reliability": metrics["grid_reliability_score"] or 0,
            }
        )
    allocation_ranked = sorted(rows, key=lambda item: item["allocation"], reverse=True)
    stress_ranked = sorted(rows, key=lambda item: item["stress"])
    reliability_ranked = sorted(rows, key=lambda item: item["reliability"], reverse=True)
    return {
        "allocation_rank": next((index for index, row in enumerate(allocation_ranked, 1) if row["slug"] == target_slug), None),
        "stress_rank": next((index for index, row in enumerate(stress_ranked, 1) if row["slug"] == target_slug), None),
        "reliability_rank": next((index for index, row in enumerate(reliability_ranked, 1) if row["slug"] == target_slug), None),
        "peer_count": len(rows),
    }


def _risk_classification(metrics: dict[str, Any]) -> str:
    stress = metrics.get("infrastructure_stress_score")
    transformer = metrics.get("transformer_risk_score")
    reliability = metrics.get("grid_reliability_score")
    if stress is None or transformer is None:
        return "unknown"
    if stress >= 80 or transformer >= 80 or (reliability is not None and reliability < 35):
        return "critical"
    if stress >= 65 or transformer >= 65:
        return "elevated"
    if stress >= 50 or transformer >= 50:
        return "watch"
    return "normal"


def _analysis_summary(name: str, scope: str, stats: dict[str, Any], metrics: dict[str, Any], trend: dict[str, Any], rankings: dict[str, Any]) -> str:
    allocation = stats.get("latest_mw")
    reliability = metrics.get("grid_reliability_score")
    stress = metrics.get("infrastructure_stress_score")
    risk = _risk_classification(metrics)
    rank = rankings.get("allocation_rank")
    peer_count = rankings.get("peer_count")
    rank_text = f"ranks {rank} of {peer_count} peers by estimated allocation" if rank else "does not yet have a peer rank"
    return (
        f"{name} {scope} currently {rank_text}. The latest estimated allocation is "
        f"{allocation if allocation is not None else 'unknown'} MW, with power availability estimated at "
        f"{metrics.get('power_availability_estimate_percent') if metrics.get('power_availability_estimate_percent') is not None else 'unknown'}%. "
        f"The recent allocation trend is {trend.get('direction')}, moving {trend.get('change_mw', 0)} MW over the sampled window. "
        f"Infrastructure stress is {stress if stress is not None else 'unknown'} and reliability is "
        f"{reliability if reliability is not None else 'unknown'}, producing a {risk} geography risk classification. "
        f"This is an automated planning-grade summary from DisCo allocation shares, population assumptions, and public grid readings."
    )


def list_states() -> list[dict[str, Any]]:
    return [
        {
            "name": profile["name"],
            "short_name": _profile_display(profile),
            "slug": slug,
            "region": REGION_LABELS[profile["region"]],
            "url": f"/state/{slug}",
            "responsible_discos": _responsible_discos(profile),
        }
        for slug, profile in sorted(STATE_PROFILES.items(), key=lambda item: item[1]["name"])
    ]


def _region_state_slugs(region_slug: str) -> list[str]:
    if region_slug not in REGION_LABELS:
        raise GeographyNotFound(f"Region not found: {region_slug}")
    return [slug for slug, profile in STATE_PROFILES.items() if profile["region"] == region_slug]


def _combined_profile(name: str, region_slug: str, state_slugs: list[str]) -> dict[str, Any]:
    population = sum(STATE_PROFILES[slug]["population_m"] for slug in state_slugs)
    shares: dict[str, float] = {}
    growth = 0.0
    settlement = 0.0
    urban = 0.0
    industrial = 0.0
    for slug in state_slugs:
        profile = STATE_PROFILES[slug]
        weight = profile["population_m"] / population if population else 0
        growth += profile["growth"] * weight
        settlement += profile["settlement"] * weight
        urban += profile["urban"] * weight
        industrial += profile["industrial"] * weight
        for disco, share in profile["discos"].items():
            shares[disco] = shares.get(disco, 0.0) + share
    return {
        "name": name,
        "region": region_slug,
        "population_m": population,
        "growth": growth,
        "settlement": settlement,
        "urban": urban,
        "industrial": industrial,
        "discos": shares,
    }


def list_regions() -> list[dict[str, Any]]:
    regions = []
    for slug, name in REGION_LABELS.items():
        state_slugs = _region_state_slugs(slug)
        regions.append(
            {
                "name": name,
                "slug": slug,
                "url": f"/region/{slug}",
                "state_count": len(state_slugs),
                "states": [STATE_PROFILES[state_slug]["name"] for state_slug in state_slugs],
            }
        )
    return regions


def state_intelligence(slug: str, hours: float = 168, limit: int = 1000) -> dict[str, Any]:
    slug = slugify_entity(slug)
    profile = STATE_PROFILES.get(slug)
    if not profile:
        raise GeographyNotFound(f"State not found: {slug}")
    history = _history_for_profile(profile, hours, limit)
    stats = _stats(history)
    metrics = _metrics(profile, stats["latest_mw"])
    latest_snapshot = GridSnapshot.query.order_by(GridSnapshot.reading_timestamp.desc()).first()
    allocation, components = _estimate_allocation(profile, _snapshot_allocations(latest_snapshot)) if latest_snapshot else (None, [])
    trend = _trend(history)
    forecast = _forecast(history)
    rankings = _rankings(slug, latest_snapshot)
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
    }


def region_intelligence(slug: str, hours: float = 168, limit: int = 1000) -> dict[str, Any]:
    slug = slugify_entity(slug)
    state_slugs = _region_state_slugs(slug)
    profile = _combined_profile(REGION_LABELS[slug], slug, state_slugs)
    history = _history_for_profile(profile, hours, limit)
    stats = _stats(history)
    metrics = _metrics(profile, stats["latest_mw"])
    trend = _trend(history)
    forecast = _forecast(history)
    latest_snapshot = GridSnapshot.query.order_by(GridSnapshot.reading_timestamp.desc()).first()
    allocation, components = _estimate_allocation(profile, _snapshot_allocations(latest_snapshot)) if latest_snapshot else (None, [])
    rankings = {
        "allocation_rank": None,
        "stress_rank": None,
        "reliability_rank": None,
        "peer_count": len(REGION_LABELS),
    }
    region_rows = []
    if latest_snapshot:
        allocations = _snapshot_allocations(latest_snapshot)
        for region_slug, region_name in REGION_LABELS.items():
            combined = _combined_profile(region_name, region_slug, _region_state_slugs(region_slug))
            estimated, _ = _estimate_allocation(combined, allocations)
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
    }
