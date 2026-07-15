from grid_monitor.services.articles import list_articles
from grid_monitor.services.entity_intelligence import list_entities
from grid_monitor.services.state_intelligence import list_regions, list_states


CONTENT_PAGE_SLUGS = (
    "about",
    "contact",
    "privacy-policy",
    "terms-of-use",
    "methodology",
    "data-sources",
)


def _absolute_url(base_url: str, path: str) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{normalized_path}"


def public_url_entries(base_url: str) -> list[dict[str, str]]:
    entries = [
        {"loc": _absolute_url(base_url, "/"), "changefreq": "hourly", "priority": "1.0"},
    ]
    entries.extend(
        {
            "loc": _absolute_url(base_url, page),
            "changefreq": "monthly",
            "priority": "0.7",
        }
        for page in CONTENT_PAGE_SLUGS
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, path),
            "changefreq": "daily",
            "priority": "0.8",
        }
        for path in ("/states", "/regions", "/geography", "/discos", "/gencos", "/articles")
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, article["url"]),
            "changefreq": "monthly",
            "priority": "0.7",
        }
        for article in list_articles()
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, state["url"]),
            "changefreq": "daily",
            "priority": "0.7",
        }
        for state in list_states()
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, region["url"]),
            "changefreq": "daily",
            "priority": "0.7",
        }
        for region in list_regions()
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, f"/geography/state/{state['slug']}"),
            "changefreq": "daily",
            "priority": "0.7",
        }
        for state in list_states()
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, entity["url"]),
            "changefreq": "daily",
            "priority": "0.7",
        }
        for entity in list_entities("disco")
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, entity["url"]),
            "changefreq": "daily",
            "priority": "0.7",
        }
        for entity in list_entities("genco")
    )
    entries.extend(
        {
            "loc": _absolute_url(base_url, path),
            "changefreq": changefreq,
            "priority": priority,
        }
        for path, changefreq, priority in (
            ("/api/metadata", "daily", "0.4"),
            ("/api/distribution", "hourly", "0.5"),
        )
    )
    return entries


def public_urls(base_url: str) -> list[str]:
    return [entry["loc"] for entry in public_url_entries(base_url)]
