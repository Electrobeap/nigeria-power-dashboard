from __future__ import annotations

from typing import Any

from flask import current_app


SITE_NAME = "Nigeria Power Data"
SITE_DESCRIPTION = (
    "Real-time Nigerian electricity generation, distribution allocation, grid health, "
    "and power infrastructure intelligence."
)


def _absolute_url(path: str) -> str:
    base_url = current_app.config["APP_BASE_URL"].rstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url}{normalized_path}"


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, child in value.items()
            if (cleaned := _clean(child)) not in (None, [], {})
        }
    if isinstance(value, list):
        return [cleaned for child in value if (cleaned := _clean(child)) not in (None, [], {})]
    return value


def _organization(base_url: str) -> dict[str, Any]:
    return {
        "@type": "Organization",
        "@id": f"{base_url}/#organization",
        "name": SITE_NAME,
        "url": f"{base_url}/",
        "logo": {
            "@type": "ImageObject",
            "@id": f"{base_url}/#logo",
            "url": f"{base_url}/static/images/logo.png",
            "contentUrl": f"{base_url}/static/images/logo.png",
            "caption": SITE_NAME,
        },
        "image": f"{base_url}/static/images/og-image.png",
        "description": SITE_DESCRIPTION,
        "contactPoint": [
            {
                "@type": "ContactPoint",
                "contactType": "General enquiries",
                "email": current_app.config["CONTACT_EMAIL"],
                "areaServed": "NG",
                "availableLanguage": ["en"],
            },
            {
                "@type": "ContactPoint",
                "contactType": "Research and data corrections",
                "email": current_app.config["RESEARCH_EMAIL"],
                "areaServed": "NG",
                "availableLanguage": ["en"],
            },
        ],
    }


def _website(base_url: str) -> dict[str, Any]:
    return {
        "@type": "WebSite",
        "@id": f"{base_url}/#website",
        "url": f"{base_url}/",
        "name": SITE_NAME,
        "description": SITE_DESCRIPTION,
        "publisher": {"@id": f"{base_url}/#organization"},
        "inLanguage": "en",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{base_url}/api/geography/search?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def _datasets(base_url: str) -> list[dict[str, Any]]:
    catalog = {"@id": f"{base_url}/data-sources#data-catalog"}
    common = {
        "creator": {"@id": f"{base_url}/#organization"},
        "publisher": {"@id": f"{base_url}/#organization"},
        "isAccessibleForFree": True,
        "inLanguage": "en",
        "license": f"{base_url}/terms-of-use",
        "includedInDataCatalog": catalog,
        "spatialCoverage": {
            "@type": "Country",
            "name": "Nigeria",
            "identifier": "NG",
        },
        "keywords": [
            "Nigeria electricity",
            "NIGGRID",
            "NISO",
            "power generation",
            "DisCo allocation",
            "GenCo output",
            "transformer loading",
        ],
    }
    return [
        {
            "@type": "DataCatalog",
            "@id": f"{base_url}/data-sources#data-catalog",
            "name": "Nigeria Power Data Electricity Data Catalog",
            "url": f"{base_url}/data-sources",
            "description": "Catalog of public Nigerian electricity datasets and planning-grade analytics exposed by Nigeria Power Data.",
            "publisher": {"@id": f"{base_url}/#organization"},
        },
        {
            "@type": "Dataset",
            "@id": f"{base_url}/#dataset-generation-history",
            **common,
            "name": "Nigeria Electricity Generation History",
            "description": "Historical total generation readings, moving averages, daily high and low generation, and grid health analytics from public NISO/NIGGRID signals.",
            "url": f"{base_url}/api/generation?hours=24&limit=288",
            "measurementTechnique": "Public source scraping, timestamped storage, and rolling statistical analytics.",
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentUrl": f"{base_url}/api/generation?hours=24&limit=288",
            },
        },
        {
            "@type": "Dataset",
            "@id": f"{base_url}/#dataset-disco-allocation",
            **common,
            "name": "Nigeria DisCo Allocation and Transformer Loading Dataset",
            "description": "Distribution company allocation readings, transformer utilization estimates, settlement growth pressure, and overload risk classification.",
            "url": f"{base_url}/api/distribution?hours=168&limit=336",
            "measurementTechnique": "DisCo allocation extraction combined with planning-grade transformer loading and settlement growth assumptions.",
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentUrl": f"{base_url}/api/distribution?hours=168&limit=336",
            },
        },
        {
            "@type": "Dataset",
            "@id": f"{base_url}/#dataset-genco-output",
            **common,
            "name": "Nigeria GenCo Output Dataset",
            "description": "Plant and generation company output readings with rankings, volatility, trend, and forecast analytics.",
            "url": f"{base_url}/api/gencos",
            "measurementTechnique": "Public generation dashboard extraction and historical performance analytics.",
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentUrl": f"{base_url}/api/gencos",
            },
        },
        {
            "@type": "Dataset",
            "@id": f"{base_url}/#dataset-geographic-intelligence",
            **common,
            "name": "Nigeria Geographic Power Intelligence Dataset",
            "description": "State, regional, LGA, town, community, and settlement-level planning estimates for demand, population served, transformer loading, grid health, and infrastructure upgrades.",
            "url": f"{base_url}/api/geography/map",
            "measurementTechnique": "Replaceable geographic hierarchy model derived from state profiles, DisCo coverage, demand assumptions, and transformer loading estimates.",
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentUrl": f"{base_url}/api/geography/map",
            },
        },
    ]


def _breadcrumb(url: str, breadcrumbs: list[dict[str, str]]) -> dict[str, Any]:
    if not breadcrumbs:
        breadcrumbs = [{"name": "Home", "path": "/"}]
    return {
        "@type": "BreadcrumbList",
        "@id": f"{url}#breadcrumb",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": item["name"],
                "item": _absolute_url(item["path"]),
            }
            for position, item in enumerate(breadcrumbs, start=1)
        ],
    }


def _webpage(
    *,
    base_url: str,
    url: str,
    title: str,
    description: str,
    page_type: str,
    include_datasets: bool,
) -> dict[str, Any]:
    page = {
        "@type": page_type,
        "@id": f"{url}#webpage",
        "url": url,
        "name": title,
        "description": description,
        "isPartOf": {"@id": f"{base_url}/#website"},
        "about": {"@id": f"{base_url}/#organization"},
        "publisher": {"@id": f"{base_url}/#organization"},
        "primaryImageOfPage": {
            "@type": "ImageObject",
            "url": f"{base_url}/static/images/og-image.png",
        },
        "breadcrumb": {"@id": f"{url}#breadcrumb"},
        "inLanguage": "en",
    }
    if include_datasets:
        page["mainEntity"] = [
            {"@id": f"{base_url}/#dataset-generation-history"},
            {"@id": f"{base_url}/#dataset-disco-allocation"},
            {"@id": f"{base_url}/#dataset-genco-output"},
            {"@id": f"{base_url}/#dataset-geographic-intelligence"},
        ]
    return page


def _article(
    *,
    base_url: str,
    url: str,
    title: str,
    description: str,
    article_type: str,
    sections: list[str] | None,
    date_published: str | None = None,
    date_modified: str | None = None,
    keywords: list[str] | None = None,
    image_path: str | None = None,
) -> dict[str, Any]:
    return {
        "@type": article_type,
        "@id": f"{url}#article",
        "mainEntityOfPage": {"@id": f"{url}#webpage"},
        "headline": title,
        "description": description,
        "image": _absolute_url(image_path or "/static/images/og-image.png"),
        "articleSection": sections,
        "keywords": keywords,
        "author": {"@id": f"{base_url}/#organization"},
        "publisher": {"@id": f"{base_url}/#organization"},
        "datePublished": date_published or current_app.config["SCHEMA_DATE_PUBLISHED"],
        "dateModified": date_modified or current_app.config["SCHEMA_DATE_MODIFIED"],
        "inLanguage": "en",
    }


def _faq(url: str, faq_items: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "@type": "FAQPage",
        "@id": f"{url}#faq",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item["answer"],
                },
            }
            for item in faq_items
        ],
    }


def build_structured_data(
    *,
    title: str,
    description: str,
    path: str,
    breadcrumbs: list[dict[str, str]] | None = None,
    page_type: str = "WebPage",
    include_datasets: bool = True,
    article_type: str | None = None,
    article_sections: list[str] | None = None,
    article_date_published: str | None = None,
    article_date_modified: str | None = None,
    article_keywords: list[str] | None = None,
    article_image_path: str | None = None,
    faq_items: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    base_url = current_app.config["APP_BASE_URL"].rstrip("/")
    url = _absolute_url(path)
    graph: list[dict[str, Any]] = [
        _organization(base_url),
        _website(base_url),
        _webpage(
            base_url=base_url,
            url=url,
            title=title,
            description=description,
            page_type=page_type,
            include_datasets=include_datasets,
        ),
        _breadcrumb(url, breadcrumbs or []),
    ]
    if include_datasets:
        graph.extend(_datasets(base_url))
    if article_type:
        graph.append(
            _article(
                base_url=base_url,
                url=url,
                title=title,
                description=description,
                article_type=article_type,
                sections=article_sections,
                date_published=article_date_published,
                date_modified=article_date_modified,
                keywords=article_keywords,
                image_path=article_image_path,
            )
        )
    if faq_items:
        graph.append(_faq(url, faq_items))
    return _clean({"@context": "https://schema.org", "@graph": graph})
