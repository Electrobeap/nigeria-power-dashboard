import json
import math
import time
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context
from sqlalchemy.orm import selectinload

from grid_monitor.models import GridSnapshot
from grid_monitor.services.entity_intelligence import slugify_entity
from grid_monitor.services.state_intelligence import (
    DISCO_LABELS,
    REGION_LABELS,
    STATE_PROFILES,
    _estimate_allocation,
    _snapshot_allocations,
)
from grid_monitor.utils.time import utc_now_iso


LEVEL_ORDER = ("state", "lga", "town", "community", "settlement")
LEVEL_LABELS = {
    "state": "State",
    "lga": "LGA",
    "town": "Town/City",
    "community": "Community",
    "settlement": "Settlement",
}
CHILD_LEVELS = {
    "state": "lga",
    "lga": "town",
    "town": "community",
    "community": "settlement",
}

_nodes_cache: list[dict[str, Any]] | None = None
_nodes_cache_signature: tuple[Any, ...] | None = None
_state_allocation_cache: dict[str, Any] = {
    "snapshot_id": None,
    "allocations": {},
    "checked_at": 0.0,
}


class HierarchyNotFound(ValueError):
    pass


STATE_MAP_COORDINATES = {
    "sokoto": (27, 10),
    "kebbi": (19, 25),
    "zamfara": (33, 24),
    "katsina": (43, 15),
    "kano": (52, 22),
    "jigawa": (62, 18),
    "kaduna": (43, 38),
    "niger": (30, 49),
    "kwara": (25, 64),
    "fct": (46, 56),
    "nasarawa": (55, 59),
    "plateau": (60, 48),
    "benue": (58, 72),
    "kogi": (45, 72),
    "oyo": (28, 80),
    "osun": (36, 82),
    "ekiti": (43, 80),
    "ondo": (42, 89),
    "ogun": (25, 91),
    "lagos": (22, 95),
    "edo": (48, 91),
    "delta": (53, 94),
    "bayelsa": (58, 96),
    "rivers": (65, 95),
    "akwa-ibom": (77, 95),
    "cross-river": (83, 91),
    "abia": (70, 91),
    "imo": (65, 90),
    "anambra": (60, 84),
    "enugu": (66, 79),
    "ebonyi": (73, 82),
    "bauchi": (67, 36),
    "gombe": (74, 47),
    "yobe": (78, 23),
    "borno": (88, 32),
    "adamawa": (82, 62),
    "taraba": (74, 68),
}


LOCALITY_SEEDS = {
    "abia": [("Umuahia North", ("Umuahia", "Ohuhu")), ("Aba North", ("Aba", "Ariaria")), ("Ohafia", ("Ohafia", "Abiriba"))],
    "adamawa": [("Yola North", ("Yola", "Jimeta")), ("Mubi North", ("Mubi", "Vimtim")), ("Numan", ("Numan", "Demsa"))],
    "akwa-ibom": [("Uyo", ("Uyo", "Itam")), ("Eket", ("Eket", "Ibeno")), ("Ikot Ekpene", ("Ikot Ekpene", "Essien Udim"))],
    "anambra": [("Awka South", ("Awka", "Amawbia")), ("Onitsha North", ("Onitsha", "GRA Onitsha")), ("Nnewi North", ("Nnewi", "Otolo"))],
    "bauchi": [("Bauchi", ("Bauchi", "Wunti")), ("Katagum", ("Azare", "Madara")), ("Misau", ("Misau", "Hardawa"))],
    "bayelsa": [("Yenagoa", ("Yenagoa", "Edepie")), ("Brass", ("Brass", "Twon-Brass")), ("Ogbia", ("Ogbia", "Otuoke"))],
    "benue": [("Makurdi", ("Makurdi", "Wurukum")), ("Gboko", ("Gboko", "Mkar")), ("Otukpo", ("Otukpo", "Adoka"))],
    "borno": [("Maiduguri", ("Maiduguri", "GRA Maiduguri")), ("Jere", ("Jere", "Mairi")), ("Biu", ("Biu", "Buratai"))],
    "cross-river": [("Calabar Municipal", ("Calabar", "Marian")), ("Ikom", ("Ikom", "Four Corners")), ("Ogoja", ("Ogoja", "Mbube"))],
    "delta": [("Oshimili South", ("Asaba", "Okpanam")), ("Warri South", ("Warri", "Effurun")), ("Ughelli North", ("Ughelli", "Agbarha"))],
    "ebonyi": [("Abakaliki", ("Abakaliki", "Kpirikpiri")), ("Afikpo North", ("Afikpo", "Amasiri")), ("Ezza South", ("Onueke", "Echara"))],
    "edo": [("Oredo", ("Benin City", "GRA Benin")), ("Egor", ("Uselu", "Ugbowo")), ("Ikpoba-Okha", ("Ikpoba Hill", "Aduwawa"))],
    "ekiti": [("Ado Ekiti", ("Ado Ekiti", "Basiri")), ("Ikere", ("Ikere Ekiti", "Odo-Oja")), ("Ijero", ("Ijero Ekiti", "Ipoti"))],
    "enugu": [("Enugu North", ("Enugu", "New Haven")), ("Nsukka", ("Nsukka", "Odenigwe")), ("Nkanu West", ("Agbani", "Ozalla"))],
    "fct": [("Abuja Municipal", ("Central Area", "Garki")), ("Bwari", ("Bwari", "Kubwa")), ("Gwagwalada", ("Gwagwalada", "Zuba"))],
    "gombe": [("Gombe", ("Gombe", "Tudun Wada")), ("Billiri", ("Billiri", "Tangale")), ("Kaltungo", ("Kaltungo", "Ture"))],
    "imo": [("Owerri Municipal", ("Owerri", "Ikenegbu")), ("Orlu", ("Orlu", "Amaifeke")), ("Okigwe", ("Okigwe", "Umulolo"))],
    "jigawa": [("Dutse", ("Dutse", "Takur")), ("Hadejia", ("Hadejia", "Majema")), ("Birnin Kudu", ("Birnin Kudu", "Kiyawa"))],
    "kaduna": [("Kaduna North", ("Kaduna", "Doka")), ("Zaria", ("Zaria", "Samaru")), ("Chikun", ("Sabon Tasha", "Kujama"))],
    "kano": [("Kano Municipal", ("Kano", "Sabon Gari")), ("Nasarawa", ("Nasarawa Kano", "Hotoro")), ("Fagge", ("Fagge", "Kwari Market"))],
    "katsina": [("Katsina", ("Katsina", "Kofar Kaura")), ("Daura", ("Daura", "Sabon Gari Daura")), ("Funtua", ("Funtua", "Dandume"))],
    "kebbi": [("Birnin Kebbi", ("Birnin Kebbi", "Gesse")), ("Argungu", ("Argungu", "Kokani")), ("Yauri", ("Yauri", "Tondi"))],
    "kogi": [("Lokoja", ("Lokoja", "Ganaja")), ("Okene", ("Okene", "Adavi")), ("Idah", ("Idah", "Anyigba"))],
    "kwara": [("Ilorin West", ("Ilorin", "Adewole")), ("Offa", ("Offa", "Erin-Ile")), ("Moro", ("Bode Saadu", "Jebba"))],
    "lagos": [("Ikeja", ("Ikeja", "Alausa")), ("Eti-Osa", ("Victoria Island", "Lekki")), ("Lagos Mainland", ("Yaba", "Ebute Metta"))],
    "nasarawa": [("Lafia", ("Lafia", "Shabu")), ("Keffi", ("Keffi", "Angwan Rimi")), ("Akwanga", ("Akwanga", "Andaha"))],
    "niger": [("Chanchaga", ("Minna", "Tunga")), ("Suleja", ("Suleja", "Madalla")), ("Bida", ("Bida", "Wadata"))],
    "ogun": [("Abeokuta South", ("Abeokuta", "Asero")), ("Ado-Odo/Ota", ("Ota", "Agbara")), ("Ifo", ("Ifo", "Sango"))],
    "ondo": [("Akure South", ("Akure", "Alagbaka")), ("Ondo West", ("Ondo", "Yaba Ondo")), ("Owo", ("Owo", "Emure-Ile"))],
    "osun": [("Osogbo", ("Osogbo", "Oke-Fia")), ("Ife Central", ("Ile-Ife", "Mayfair")), ("Ilesa East", ("Ilesa", "Ijebu-Jesa"))],
    "oyo": [("Ibadan North", ("Ibadan", "Bodija")), ("Ogbomoso North", ("Ogbomoso", "Sabo Ogbomoso")), ("Iseyin", ("Iseyin", "Ado-Awaye"))],
    "plateau": [("Jos North", ("Jos", "Terminus")), ("Jos South", ("Bukuru", "Rayfield")), ("Mangu", ("Mangu", "Panyam"))],
    "rivers": [("Port Harcourt", ("Port Harcourt", "Diobu")), ("Obio-Akpor", ("Rumuokoro", "Rumuodara")), ("Eleme", ("Eleme", "Onne"))],
    "sokoto": [("Sokoto North", ("Sokoto", "Runjin Sambo")), ("Wamakko", ("Wamakko", "Gumbi")), ("Tambuwal", ("Tambuwal", "Romon Sarki"))],
    "taraba": [("Jalingo", ("Jalingo", "Mayo Gwoi")), ("Wukari", ("Wukari", "Rafin Kada")), ("Bali", ("Bali", "Maihula"))],
    "yobe": [("Damaturu", ("Damaturu", "Nayinawa")), ("Potiskum", ("Potiskum", "Fika Road")), ("Nguru", ("Nguru", "Bulabulin"))],
    "zamfara": [("Gusau", ("Gusau", "Tudun Wada Gusau")), ("Kaura Namoda", ("Kaura Namoda", "Sakajiki")), ("Talata Mafara", ("Talata Mafara", "Jangebe"))],
}


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _url(level: str, slug: str) -> str:
    return f"/geography/{level}/{slug}"


def _node_slug(parent_slug: str, name: str) -> str:
    return slugify_entity(f"{parent_slug}-{name}")


def _safe_config(name: str, default: str | None = None) -> str | None:
    if not has_app_context():
        return default
    return current_app.config.get(name, default)


def _normalise_external_node(raw: dict[str, Any]) -> dict[str, Any]:
    level = raw["level"]
    slug = raw.get("slug") or slugify_entity(raw["name"])
    return {
        **raw,
        "slug": slug,
        "level": level,
        "level_label": LEVEL_LABELS.get(level, level.title()),
        "url": raw.get("url") or _url(level, slug),
        "population_m": float(raw.get("population_m") or 0),
        "state_share": float(raw.get("state_share") or 1),
        "data_source": raw.get("data_source") or "external_dataset",
    }


def _load_external_nodes() -> list[dict[str, Any]] | None:
    dataset_path = _safe_config("GEOGRAPHY_DATASET_PATH")
    if not dataset_path:
        return None
    path = Path(dataset_path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes") if isinstance(payload, dict) else payload
    if not isinstance(nodes, list):
        return None
    return [_normalise_external_node(node) for node in nodes if isinstance(node, dict)]


def _dataset_signature() -> tuple[Any, ...]:
    dataset_path = _safe_config("GEOGRAPHY_DATASET_PATH")
    if not dataset_path:
        return ("built_in_planning_seed", len(STATE_PROFILES), len(LOCALITY_SEEDS))
    path = Path(dataset_path)
    try:
        stat = path.stat()
    except OSError:
        return ("external_missing", str(path))
    return ("external_json", str(path), stat.st_mtime_ns, stat.st_size)


def _responsible_discos(discos: dict[str, float]) -> list[dict[str, Any]]:
    return [
        {
            "name": DISCO_LABELS.get(key, key.replace("_", " ").title()),
            "slug": slugify_entity(DISCO_LABELS.get(key, key)),
            "share_of_state_percent": _round(share * 100, 1),
            "url": f"/discos/{slugify_entity(DISCO_LABELS.get(key, key))}",
        }
        for key, share in discos.items()
    ]


def _state_node(state_slug: str, profile: dict[str, Any]) -> dict[str, Any]:
    x, y = STATE_MAP_COORDINATES.get(state_slug, (50, 50))
    return {
        "slug": state_slug,
        "level": "state",
        "level_label": LEVEL_LABELS["state"],
        "name": profile["name"],
        "short_name": profile.get("short_name") or profile["name"],
        "parent_slug": None,
        "parent_level": None,
        "state_slug": state_slug,
        "state_name": profile["name"],
        "region_slug": profile["region"],
        "region": REGION_LABELS[profile["region"]],
        "population_m": profile["population_m"],
        "state_share": 1.0,
        "growth": profile["growth"],
        "settlement": profile["settlement"],
        "urban": profile["urban"],
        "industrial": profile["industrial"],
        "discos": profile["discos"],
        "map_x": x,
        "map_y": y,
        "url": _url("state", state_slug),
        "legacy_url": f"/state/{state_slug}",
        "data_source": "planning_seed",
    }


def _make_child(
    parent: dict[str, Any],
    level: str,
    name: str,
    weight: float,
    index: int,
    total_weight: float,
) -> dict[str, Any]:
    share = weight / total_weight if total_weight else 0
    variation = index - 1
    slug = _node_slug(parent["slug"], name)
    population_m = parent["population_m"] * share
    return {
        "slug": slug,
        "level": level,
        "level_label": LEVEL_LABELS[level],
        "name": name,
        "short_name": name,
        "parent_slug": parent["slug"],
        "parent_level": parent["level"],
        "state_slug": parent["state_slug"],
        "state_name": parent["state_name"],
        "region_slug": parent["region_slug"],
        "region": parent["region"],
        "population_m": population_m,
        "state_share": parent["state_share"] * share,
        "growth": max(1.2, parent["growth"] + (0.16 * variation)),
        "settlement": max(10, min(98, parent["settlement"] + (4.0 * variation))),
        "urban": max(0.15, min(0.98, parent["urban"] + (0.035 * variation))),
        "industrial": max(0.08, min(0.98, parent["industrial"] + (0.045 * variation))),
        "discos": parent["discos"],
        "url": _url(level, slug),
        "data_source": "planning_seed",
    }


def _community_names(town_name: str) -> tuple[str, str]:
    return (f"{town_name} Central", f"{town_name} Extension")


def _settlement_names(community_name: str) -> tuple[str, str]:
    return (f"{community_name} Feeder Zone", f"{community_name} Growth Area")


def _built_in_nodes() -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for state_slug, profile in STATE_PROFILES.items():
        state = _state_node(state_slug, profile)
        nodes.append(state)
        lgas = LOCALITY_SEEDS.get(
            state_slug,
            [
                (f"{profile['name']} Central", (profile["name"], f"{profile['name']} Market")),
                (f"{profile['name']} North", (f"North {profile['name']}", f"{profile['name']} Junction")),
                (f"{profile['name']} South", (f"South {profile['name']}", f"{profile['name']} Estate")),
            ],
        )
        lga_weights = (0.42, 0.33, 0.25)
        total_lga_weight = sum(lga_weights[: len(lgas)])
        for lga_index, (lga_name, towns) in enumerate(lgas, start=1):
            lga = _make_child(state, "lga", lga_name, lga_weights[lga_index - 1], lga_index, total_lga_weight)
            nodes.append(lga)
            town_weights = (0.58, 0.42)
            total_town_weight = sum(town_weights[: len(towns)])
            for town_index, town_name in enumerate(towns, start=1):
                town = _make_child(lga, "town", town_name, town_weights[town_index - 1], town_index, total_town_weight)
                nodes.append(town)
                community_weights = (0.56, 0.44)
                for community_index, community_name in enumerate(_community_names(town_name), start=1):
                    community = _make_child(
                        town,
                        "community",
                        community_name,
                        community_weights[community_index - 1],
                        community_index,
                        sum(community_weights),
                    )
                    nodes.append(community)
                    settlement_weights = (0.62, 0.38)
                    for settlement_index, settlement_name in enumerate(_settlement_names(community_name), start=1):
                        nodes.append(
                            _make_child(
                                community,
                                "settlement",
                                settlement_name,
                                settlement_weights[settlement_index - 1],
                                settlement_index,
                                sum(settlement_weights),
                            )
                        )
    return nodes


def hierarchy_nodes() -> list[dict[str, Any]]:
    global _nodes_cache, _nodes_cache_signature

    signature = _dataset_signature()
    if _nodes_cache is not None and _nodes_cache_signature == signature:
        return _nodes_cache

    _nodes_cache = _load_external_nodes() or _built_in_nodes()
    _nodes_cache_signature = signature
    return _nodes_cache


def _index_by_slug(nodes: list[dict[str, Any]] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    nodes = nodes or hierarchy_nodes()
    return {(node["level"], node["slug"]): node for node in nodes}


def _children(parent: dict[str, Any], nodes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    child_level = CHILD_LEVELS.get(parent["level"])
    if not child_level:
        return []
    nodes = nodes or hierarchy_nodes()
    return [
        node
        for node in nodes
        if node.get("level") == child_level and node.get("parent_slug") == parent["slug"]
    ]


def _find_node(
    level: str,
    slug: str,
    index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    level = slugify_entity(level)
    slug = slugify_entity(slug)
    node = (index or _index_by_slug()).get((level, slug))
    if not node:
        raise HierarchyNotFound(f"{LEVEL_LABELS.get(level, 'Geography')} not found: {slug}")
    return node


def _latest_state_allocations() -> dict[str, float | None]:
    global _state_allocation_cache

    now = time.time()
    if (
        _state_allocation_cache["checked_at"] > 0
        and now - _state_allocation_cache["checked_at"] <= 30
    ):
        return _state_allocation_cache["allocations"]

    try:
        latest_snapshot = (
            GridSnapshot.query.options(selectinload(GridSnapshot.disco_data))
            .order_by(GridSnapshot.reading_timestamp.desc())
            .first()
        )
    except Exception:
        _state_allocation_cache = {"snapshot_id": None, "allocations": {}, "checked_at": now}
        return {}
    if not latest_snapshot:
        _state_allocation_cache = {"snapshot_id": None, "allocations": {}, "checked_at": now}
        return {}
    if _state_allocation_cache["snapshot_id"] == latest_snapshot.id:
        _state_allocation_cache["checked_at"] = now
        return _state_allocation_cache["allocations"]

    disco_allocations = _snapshot_allocations(latest_snapshot)
    allocations: dict[str, float | None] = {}
    for state_slug, profile in STATE_PROFILES.items():
        allocation, _ = _estimate_allocation(profile, disco_allocations)
        allocations[state_slug] = allocation
    _state_allocation_cache = {
        "snapshot_id": latest_snapshot.id,
        "allocations": allocations,
        "checked_at": now,
    }
    return allocations


def _latest_state_allocation(state_slug: str) -> float | None:
    return _latest_state_allocations().get(state_slug)


def _estimated_peak_demand(node: dict[str, Any]) -> float:
    demand_per_million = 45 + (75 * node["urban"]) + (35 * node["industrial"])
    return node["population_m"] * demand_per_million


def _baseline_allocation(node: dict[str, Any], peak_demand: float) -> float:
    availability = 0.28 + (node["urban"] * 0.12) + (node["industrial"] * 0.08)
    return peak_demand * max(0.22, min(0.52, availability))


def _metrics(node: dict[str, Any]) -> dict[str, Any]:
    peak_demand = _estimated_peak_demand(node)
    state_allocation = _latest_state_allocation(node["state_slug"])
    if state_allocation is None:
        allocation = _baseline_allocation(node, peak_demand)
        allocation_source = "model_baseline_no_stored_reading"
    else:
        allocation = state_allocation * node["state_share"]
        allocation_source = "latest_disco_allocation_scaled_to_hierarchy"
    current_demand = peak_demand * (0.66 + node["urban"] * 0.10 + node["industrial"] * 0.08)
    availability = (allocation / peak_demand) * 100 if peak_demand else None
    transformer_loading = min(
        140,
        max(
            25,
            58
            + (node["settlement"] * 0.22)
            + (node["growth"] * 3.1)
            + (node["industrial"] * 12)
            - ((availability or 0) * 0.12),
        ),
    )
    grid_health = min(
        100,
        max(
            0,
            96
            - (transformer_loading * 0.45)
            - (node["settlement"] * 0.10)
            + ((availability or 0) * 0.28),
        ),
    )
    projected_12m = current_demand * (1 + node["growth"] / 100)
    projected_36m = current_demand * ((1 + node["growth"] / 100) ** 3)
    return {
        "estimated_population": int(round(node["population_m"] * 1_000_000)),
        "estimated_population_m": _round(node["population_m"], 3),
        "estimated_current_demand_mw": _round(current_demand),
        "estimated_peak_demand_mw": _round(peak_demand),
        "estimated_allocation_mw": _round(allocation),
        "allocation_source": allocation_source,
        "power_availability_percent": _round(min(100, availability) if availability is not None else None, 1),
        "projected_demand_growth_percent": _round(node["growth"], 1),
        "projected_12m_demand_mw": _round(projected_12m),
        "projected_36m_demand_mw": _round(projected_36m),
        "transformer_loading_percent": _round(transformer_loading, 1),
        "grid_health_score": _round(grid_health, 1),
        "infrastructure_stress_score": _round(100 - grid_health, 1),
        "settlement_growth_indicator": _round(node["settlement"], 1),
    }


def _classification(metrics: dict[str, Any]) -> str:
    loading = metrics["transformer_loading_percent"] or 0
    health = metrics["grid_health_score"] or 0
    if loading >= 96 or health < 35:
        return "critical"
    if loading >= 86 or health < 50:
        return "elevated"
    if loading >= 76 or health < 65:
        return "watch"
    return "stable"


def _recommended_upgrades(node: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, str]]:
    loading = metrics["transformer_loading_percent"] or 0
    growth = metrics["projected_demand_growth_percent"] or 0
    level_label = LEVEL_LABELS[node["level"]]
    upgrades = [
        {
            "priority": "Data",
            "title": f"Validate {level_label.lower()} feeder and transformer inventory",
            "rationale": "Replace planning estimates with official feeder, DT, customer, and transformer loading records.",
        }
    ]
    if loading >= 96:
        upgrades.extend(
            [
                {
                    "priority": "Critical",
                    "title": "Install or uprate distribution transformers",
                    "rationale": "Estimated loading is above overload planning threshold.",
                },
                {
                    "priority": "Critical",
                    "title": "Rebalance overloaded 11 kV feeders",
                    "rationale": "High loading and demand growth indicate near-term reliability pressure.",
                },
            ]
        )
    elif loading >= 86:
        upgrades.extend(
            [
                {
                    "priority": "High",
                    "title": "Add transformer capacity in growth corridors",
                    "rationale": "Loading is approaching overload threshold under projected demand.",
                },
                {
                    "priority": "High",
                    "title": "Deploy feeder monitoring and protection review",
                    "rationale": "Monitoring improves outage detection and load-transfer decisions.",
                },
            ]
        )
    else:
        upgrades.append(
            {
                "priority": "Medium",
                "title": "Prepare phased capacity reinforcement plan",
                "rationale": "Current loading is manageable but settlement expansion should be tracked.",
            }
        )
    if growth >= 3.5:
        upgrades.append(
            {
                "priority": "Growth",
                "title": "Reserve transformer and feeder capacity for settlement expansion",
                "rationale": "Projected demand growth is above the national planning baseline used by the model.",
            }
        )
    return upgrades


def _breadcrumbs(
    node: dict[str, Any],
    index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    index = index or _index_by_slug()
    chain = [node]
    parent_slug = node.get("parent_slug")
    parent_level = node.get("parent_level")
    while parent_slug and parent_level:
        parent = index.get((parent_level, parent_slug))
        if not parent:
            break
        chain.append(parent)
        parent_slug = parent.get("parent_slug")
        parent_level = parent.get("parent_level")
    return [
        {"name": item["name"], "level": item["level"], "level_label": LEVEL_LABELS[item["level"]], "url": item["url"]}
        for item in reversed(chain)
    ]


def _summary_node(node: dict[str, Any], include_metrics: bool = False) -> dict[str, Any]:
    payload = {
        "name": node["name"],
        "short_name": node.get("short_name") or node["name"],
        "slug": node["slug"],
        "level": node["level"],
        "level_label": LEVEL_LABELS[node["level"]],
        "url": node["url"],
        "state": node["state_name"],
        "region": node["region"],
    }
    if node["level"] == "state":
        payload["map_x"] = node.get("map_x")
        payload["map_y"] = node.get("map_y")
        payload["legacy_url"] = node.get("legacy_url")
    if include_metrics:
        metrics = _metrics(node)
        payload["metrics"] = metrics
        payload["risk_classification"] = _classification(metrics)
    return payload


def hierarchy_overview() -> dict[str, Any]:
    nodes = hierarchy_nodes()
    states = [node for node in nodes if node["level"] == "state"]
    return {
        "generated_at": utc_now_iso(),
        "dataset": data_lineage(),
        "levels": [{"key": level, "label": LEVEL_LABELS[level]} for level in LEVEL_ORDER],
        "states": [_summary_node(node, include_metrics=True) for node in sorted(states, key=lambda item: item["name"])],
        "counts": hierarchy_counts(nodes),
    }


def hierarchy_counts(nodes: list[dict[str, Any]] | None = None) -> dict[str, int]:
    counts = {level: 0 for level in LEVEL_ORDER}
    for node in nodes or hierarchy_nodes():
        counts[node["level"]] = counts.get(node["level"], 0) + 1
    return counts


def data_lineage() -> dict[str, Any]:
    dataset_path = _safe_config("GEOGRAPHY_DATASET_PATH")
    return {
        "active_dataset": "external_json" if dataset_path else "built_in_planning_seed",
        "dataset_path": dataset_path,
        "replaceable": True,
        "method": "Hierarchical planning estimates derived from state demand assumptions, DisCo coverage, settlement intensity, and scaled population shares.",
    }


def hierarchy_detail(level: str, slug: str) -> dict[str, Any]:
    nodes = hierarchy_nodes()
    index = _index_by_slug(nodes)
    node = _find_node(level, slug, index)
    metrics = _metrics(node)
    children = _children(node, nodes)
    classification = _classification(metrics)
    child_level = CHILD_LEVELS.get(node["level"])
    return {
        "scope": "hierarchical_geography",
        "generated_at": utc_now_iso(),
        "entity": {
            "name": node["name"],
            "short_name": node.get("short_name") or node["name"],
            "slug": node["slug"],
            "level": node["level"],
            "level_label": LEVEL_LABELS[node["level"]],
            "url": node["url"],
            "state": node["state_name"],
            "state_slug": node["state_slug"],
            "region": node["region"],
            "region_slug": node["region_slug"],
            "parent_slug": node.get("parent_slug"),
            "parent_level": node.get("parent_level"),
        },
        "breadcrumbs": _breadcrumbs(node, index),
        "metrics": metrics,
        "coverage": {
            "responsible_discos": _responsible_discos(node["discos"]),
            "primary_disco": _responsible_discos(node["discos"])[0] if node.get("discos") else None,
        },
        "grid_health": {
            "classification": classification,
            "score": metrics["grid_health_score"],
            "transformer_loading_percent": metrics["transformer_loading_percent"],
            "infrastructure_stress_score": metrics["infrastructure_stress_score"],
        },
        "recommended_upgrades": _recommended_upgrades(node, metrics),
        "children": [_summary_node(child, include_metrics=True) for child in sorted(children, key=lambda item: item["name"])],
        "child_level": child_level,
        "siblings": [
            _summary_node(item)
            for item in nodes
            if item["level"] == node["level"] and item.get("parent_slug") == node.get("parent_slug") and item["slug"] != node["slug"]
        ][:12],
        "data_lineage": data_lineage(),
        "analysis_summary": _analysis_summary(node, metrics, classification, child_level),
    }


def _analysis_summary(node: dict[str, Any], metrics: dict[str, Any], classification: str, child_level: str | None) -> str:
    child_text = f" Drill-down continues to {LEVEL_LABELS[child_level]} planning areas." if child_level else ""
    return (
        f"{node['name']} is modelled as a {LEVEL_LABELS[node['level']]} within {node['state_name']}, {node['region']}. "
        f"Estimated population is {metrics['estimated_population']:,}, current demand is approximately "
        f"{metrics['estimated_current_demand_mw']} MW, and transformer loading is estimated at "
        f"{metrics['transformer_loading_percent']}%. Grid health is classified as {classification}. "
        f"Recommended upgrades are generated from transformer loading, settlement growth, demand growth, and DisCo coverage assumptions."
        f"{child_text}"
    )


def search_hierarchy(query: str, level: str | None = None, limit: int = 20) -> dict[str, Any]:
    q = slugify_entity(query or "")
    if not q:
        return {"query": query, "results": [], "total": 0}
    allowed_level = slugify_entity(level) if level else None
    results = []
    for node in hierarchy_nodes():
        if allowed_level and node["level"] != allowed_level:
            continue
        searchable = " ".join(
            [
                node["name"],
                node["slug"],
                node["state_name"],
                node["region"],
                LEVEL_LABELS[node["level"]],
            ]
        )
        searchable_slug = slugify_entity(searchable)
        if q in searchable_slug:
            score = 0
            if slugify_entity(node["name"]).startswith(q):
                score += 40
            if node["slug"].startswith(q):
                score += 25
            score += max(0, 10 - LEVEL_ORDER.index(node["level"]))
            results.append((score, _summary_node(node, include_metrics=True)))
    ranked = [item for _, item in sorted(results, key=lambda row: (-row[0], row[1]["name"]))[:limit]]
    return {"query": query, "results": ranked, "total": len(results)}
