from copy import deepcopy

from flask import Blueprint, Response, abort, current_app, render_template, request, send_from_directory

from grid_monitor.services.articles import (
    adjacent_articles,
    article_categories,
    featured_article,
    get_article,
    latest_articles,
    popular_articles,
    related_articles,
    related_articles_for_context,
    related_topics,
    search_articles,
)
from grid_monitor.services.entity_intelligence import (
    EntityNotFound,
    display_entity_name,
    entity_intelligence,
    list_entities,
)
from grid_monitor.services.indexnow import indexnow_key, indexnow_key_file_body
from grid_monitor.services.geographic_hierarchy import hierarchy_counts
from grid_monitor.services.site_urls import public_url_entries
from grid_monitor.services.social_meta import build_social_meta
from grid_monitor.services.state_intelligence import (
    GeographyNotFound,
    list_regions,
    list_states,
    region_intelligence,
    state_intelligence,
)
from grid_monitor.services.structured_data import build_structured_data


web_bp = Blueprint("web", __name__)


CONTENT_PAGES = {
    "about": {
        "title": "About Nigeria Power Data",
        "description": "Nigeria Power Data is an independent analytics dashboard for public Nigerian power generation and distribution signals.",
        "eyebrow": "About",
        "headline": "A public grid intelligence workspace for Nigeria's electricity market.",
        "lede": "Nigeria Power Data turns public NISO/NIGGRID readings into useful operational context for analysts, builders, journalists, researchers, and energy-market observers.",
        "sections": [
            {
                "heading": "What The Platform Does",
                "body": "The dashboard tracks generation, GenCo output, DisCo load allocation, grid health, distribution stress, and trend movement from public source data. It is designed for monitoring and research, not for real-time dispatch control.",
            },
            {
                "heading": "Why It Exists",
                "body": "Nigeria's power sector data is easier to understand when live readings are connected to history, risk indicators, rankings, and plain-language interpretation. This platform makes those signals easier to scan and revisit.",
            },
            {
                "heading": "Research And Data Contact",
                "body": "For methodology questions, data corrections, and research collaboration, email {RESEARCH_EMAIL}. For platform, partnership, or general enquiries, email {CONTACT_EMAIL}.",
            },
        ],
    },
    "contact": {
        "title": "Contact Nigeria Power Data",
        "description": "Contact information for Nigeria Power Data feedback, corrections, partnerships, and data questions.",
        "eyebrow": "Contact",
        "headline": "Questions, corrections, and collaboration are welcome.",
        "lede": "For feedback, data corrections, research collaboration, or commercial enquiries, contact the Nigeria Power Data team.",
        "sections": [
            {
                "heading": "General Contact",
                "body": "General enquiries: {CONTACT_EMAIL}. Include the page URL, timestamp, and source reading if you are reporting a data issue.",
            },
            {
                "heading": "Research And Data Corrections",
                "body": "Research collaboration and source-data corrections: {RESEARCH_EMAIL}. Because the dashboard depends on public source data, corrections should reference the original NISO/NIGGRID publication where possible.",
            },
            {
                "heading": "Advertising And Sponsorship",
                "body": "Advertising, sponsorship, and future placement enquiries: {ADS_EMAIL}.",
            },
        ],
    },
    "privacy-policy": {
        "title": "Privacy Policy",
        "description": "Privacy Policy for Nigeria Power Data.",
        "eyebrow": "Privacy",
        "headline": "Privacy-first analytics for a public information dashboard.",
        "lede": "Nigeria Power Data is designed to display public grid information with minimal user data collection.",
        "sections": [
            {
                "heading": "Information We Process",
                "body": "The platform may receive standard server logs such as request path, timestamp, user agent, and IP address from hosting infrastructure. These logs are used for security, debugging, and reliability.",
            },
            {
                "heading": "Cookies And Advertising",
                "body": "The current application does not require account cookies. If advertising or analytics tools are added later, this page should be updated before those services are enabled.",
            },
            {
                "heading": "Third-Party Sources",
                "body": "Links to source websites and external services are governed by their own privacy policies.",
            },
        ],
    },
    "terms-of-use": {
        "title": "Terms of Use",
        "description": "Terms of Use for Nigeria Power Data.",
        "eyebrow": "Terms",
        "headline": "Use this dashboard as an analytical reference, not as operational dispatch advice.",
        "lede": "By using Nigeria Power Data, you agree that the service provides public-data analysis on a best-effort basis.",
        "sections": [
            {
                "heading": "No Warranty",
                "body": "The dashboard may contain delays, source outages, parsing errors, or incomplete readings. It is provided without warranty and should be independently verified before business, regulatory, or operational use.",
            },
            {
                "heading": "Acceptable Use",
                "body": "Do not abuse the API, attempt to disrupt the service, or represent dashboard estimates as official dispatch instructions.",
            },
            {
                "heading": "Changes",
                "body": "Features, data sources, calculations, and access patterns may change as the platform matures.",
            },
        ],
    },
    "methodology": {
        "title": "Methodology",
        "description": "How Nigeria Power Data calculates grid trends, forecasts, GenCo rankings, DisCo risk, and transformer utilization indicators.",
        "eyebrow": "Methodology",
        "headline": "Transparent calculations from public source readings.",
        "lede": "The platform combines current readings, stored history, statistical summaries, and planning-grade assumptions to make the power system easier to interpret.",
        "sections": [
            {
                "heading": "Generation And Trend Metrics",
                "body": "Generation trends compare the first and latest readings inside the selected window. Moving averages smooth recent readings. Volatility uses population standard deviation as a percentage of the average.",
            },
            {
                "heading": "Forecasts",
                "body": "Entity forecasts use a simple recent linear trend. They are directional monitoring estimates, not demand forecasts, production schedules, or financial guidance.",
            },
            {
                "heading": "Distribution Intelligence",
                "body": "Transformer utilization is estimated from DisCo allocation, power factor assumptions, regional growth assumptions, and warning thresholds. It is a planning proxy, not direct transformer telemetry.",
            },
            {
                "heading": "State And Regional Intelligence",
                "body": "State and regional pages allocate DisCo load readings into geography-level planning estimates using franchise-area mappings, state demand assumptions, population proxies, settlement growth indicators, and peer rankings. Shared franchise areas are handled with explicit split weights.",
            },
            {
                "heading": "Hierarchical Geographic Intelligence",
                "body": "The interactive map uses a replaceable hierarchy from State to LGA to Town/City to Community to Settlement. Current lower-level records are planning-grade seed estimates derived from state profiles, population shares, DisCo coverage, settlement intensity, and transformer loading assumptions.",
            },
            {
                "heading": "AI-Generated Summaries",
                "body": "Analysis summaries are generated automatically from deterministic metrics such as rank, trend, volatility, forecast, and risk classification. They do not use private operational data.",
            },
        ],
    },
    "data-sources": {
        "title": "Data Sources",
        "description": "Public data sources used by Nigeria Power Data.",
        "eyebrow": "Sources",
        "headline": "Built from public Nigerian grid source readings.",
        "lede": "Nigeria Power Data currently uses public NISO/NIGGRID pages as the source for generation and distribution allocation readings.",
        "sections": [
            {
                "heading": "NIGGRID Dashboard",
                "body": "The generation dashboard is used for realtime generation, reporting GenCos, daily peak/off-peak readings, and plant-level output where available.",
            },
            {
                "heading": "DisCo Load Profile",
                "body": "The DisCo load profile page is used for distribution allocation readings and related distribution intelligence calculations.",
            },
            {
                "heading": "Franchise-Area Mapping",
                "body": "State and regional intelligence uses a planning-grade DisCo franchise-area mapping based on public NERC and DisCo franchise descriptions. It is intended for state-level analysis, not feeder-level service-territory precision.",
            },
            {
                "heading": "Geographic Hierarchy Dataset",
                "body": "The State to Settlement map is designed around replaceable JSON nodes. The built-in hierarchy uses representative planning areas and placeholder estimates until official LGA, community, feeder, transformer, and customer datasets are supplied.",
            },
            {
                "heading": "Data Freshness",
                "body": "Stored readings are collected on the configured scheduler interval. Public source downtime, layout changes, or deployment sleep can affect freshness.",
            },
        ],
    },
}


FAQ_CONTENT_PAGES = {"methodology", "data-sources"}


def _display_slug(slug):
    return slug.replace("-", " ").title()


def _labelize(value):
    return str(value or "pending").replace("_", " ").replace("-", " ").title()


def _format_mw(value, digits=0):
    if value is None:
        return "Pending"
    return f"{float(value):,.{digits}f} MW"


def _format_percent(value, digits=1):
    if value is None:
        return "Pending"
    return f"{float(value):,.{digits}f}%"


def _schema(title, description, path, breadcrumbs, **kwargs):
    return build_structured_data(
        title=title,
        description=description,
        path=path,
        breadcrumbs=breadcrumbs,
        **kwargs,
    )


def _social(
    title,
    description,
    path,
    image_path=None,
    image_alt=None,
    og_type="website",
    published_time=None,
    modified_time=None,
):
    return build_social_meta(
        title=title,
        description=description,
        path=path,
        image_path=image_path,
        image_alt=image_alt,
        og_type=og_type,
        published_time=published_time,
        modified_time=modified_time,
    )


def _report_schema(title, description, path, breadcrumbs, sections, faq_items=None):
    return _schema(
        title,
        description,
        path,
        breadcrumbs,
        page_type="WebPage",
        article_type="Article",
        article_sections=sections,
        faq_items=faq_items,
    )


def _entity_fallback_payload(entity_type, slug):
    label = "DisCo" if entity_type == "disco" else "GenCo"
    plural = "discos" if entity_type == "disco" else "gencos"
    name = display_entity_name(_display_slug(slug))
    return {
        "entity": {
            "type": entity_type,
            "label": label,
            "name": name,
            "slug": slug,
            "unit": "MW allocation" if entity_type == "disco" else "MW output",
            "url": f"/{plural}/{slug}",
        },
        "statistics": {},
        "trend": {},
        "forecast": {},
        "risk": {"classification": "pending", "primary_driver": "source_history"},
        "utilization": {},
        "rankings": {"latest": {}, "average": {}},
        "performance": {},
        "sample_count": 0,
        "analysis_summary": (
            f"{name} {label} intelligence will populate with historical trend, forecast, ranking, "
            "and risk metrics as soon as source readings are stored for this entity."
        ),
        "related": list_entities(entity_type),
    }


def _entity_seo_context(entity_type, slug):
    try:
        payload = entity_intelligence(entity_type, slug)
    except EntityNotFound:
        payload = _entity_fallback_payload(entity_type, slug)

    entity = payload["entity"]
    name = entity["name"]
    label = entity["label"]
    stats = payload.get("statistics") or {}
    trend = payload.get("trend") or {}
    forecast = payload.get("forecast") or {}
    risk = payload.get("risk") or {}
    latest_rank = (payload.get("rankings") or {}).get("latest") or {}
    performance = payload.get("performance") or {}
    distribution = (payload.get("utilization") or {}).get("distribution") or {}
    canonical_path = entity.get("url") or f"/{entity['type']}s/{slug}"

    if entity_type == "disco":
        title = f"{name} Load Allocation, Transformer Risk & Distribution Intelligence"
        description = (
            f"{name} electricity distribution intelligence with load allocation trends, transformer utilization, "
            "settlement growth pressure, grid risk signals, forecasts, and peer ranking for Nigeria."
        )
        sections = ["DisCo allocation", "Transformer utilization", "Settlement growth", "Forecast and risk"]
        facts = [
            {"label": "Latest allocation", "value": _format_mw(stats.get("latest_mw"))},
            {"label": "Transformer utilization", "value": _format_percent(distribution.get("estimated_utilization_percent"))},
            {"label": "12-month utilization forecast", "value": _format_percent(distribution.get("projected_utilization_12m_percent"))},
            {"label": "Risk classification", "value": _labelize(risk.get("classification"))},
            {"label": "Latest rank", "value": f"#{latest_rank.get('rank')} of {latest_rank.get('total_entities')}" if latest_rank.get("rank") else "Pending"},
            {"label": "24h forecast", "value": _format_mw(forecast.get("next_24h_mw"))},
        ]
        faq_items = [
            {
                "question": f"What does the {name} page track?",
                "answer": f"It tracks {name} load allocation, historical trend, transformer utilization, settlement growth pressure, forecast movement, and risk classification from stored public grid readings.",
            },
            {
                "question": f"How is {name} transformer risk estimated?",
                "answer": "Transformer risk is estimated from DisCo allocation, planning-grade utilization assumptions, settlement growth pressure, and configured warning and overload thresholds.",
            },
            {
                "question": f"Is {name} data official operational advice?",
                "answer": "No. Nigeria Power Data is an independent public-data analytics platform. Readings and estimates should be verified against official sources before operational, regulatory, or commercial decisions.",
            },
        ]
    else:
        title = f"{name} Generation Output, Forecast & Performance Intelligence"
        description = (
            f"{name} generation intelligence with output history, moving averages, volatility, rankings, forecast, "
            "and performance analytics from Nigeria Power Data."
        )
        sections = ["GenCo output", "Generation history", "Performance ranking", "Forecast and volatility"]
        facts = [
            {"label": "Latest output", "value": _format_mw(stats.get("latest_mw"))},
            {"label": "Average output", "value": _format_mw(stats.get("average_mw"))},
            {"label": "Volatility", "value": _format_percent(stats.get("volatility_percent"))},
            {"label": "Performance score", "value": f"{performance.get('score')}/100" if performance.get("score") is not None else "Pending"},
            {"label": "Latest rank", "value": f"#{latest_rank.get('rank')} of {latest_rank.get('total_entities')}" if latest_rank.get("rank") else "Pending"},
            {"label": "24h forecast", "value": _format_mw(forecast.get("next_24h_mw"))},
        ]
        faq_items = [
            {
                "question": f"What does the {name} GenCo page show?",
                "answer": f"It shows {name} output history, moving average, volatility, ranking, short-term forecast, and automated performance analysis from stored generation readings.",
            },
            {
                "question": f"How is {name} performance ranked?",
                "answer": "Ranking compares latest and average stored output against other generation entities captured by the platform during the selected history window.",
            },
            {
                "question": f"How often is {name} generation intelligence updated?",
                "answer": "The page updates as new public NISO/NIGGRID readings are fetched and stored by the platform scheduler.",
            },
        ]

    breadcrumbs = [
        {"name": "Home", "path": "/"},
        {"name": f"{label} Intelligence", "path": f"/{entity['type']}s"},
        {"name": name, "path": canonical_path},
    ]
    return {
        "payload": payload,
        "title": title,
        "description": description,
        "canonical_path": canonical_path,
        "breadcrumbs": breadcrumbs,
        "sections": sections,
        "faq_items": faq_items,
        "content": {
            "eyebrow": f"{label} SEO Intelligence",
            "h1": title,
            "lede": description,
            "summary": payload.get("analysis_summary"),
            "facts": facts,
            "faq_items": faq_items,
            "breadcrumbs": breadcrumbs,
        },
    }


def _geo_seo_context(scope, slug):
    try:
        payload = state_intelligence(slug) if scope == "state" else region_intelligence(slug)
    except GeographyNotFound:
        abort(404)

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
        {"label": "Transformer risk score", "value": f"{metrics.get('transformer_risk_score')}/100" if metrics.get("transformer_risk_score") is not None else "Pending"},
        {"label": "Reliability rank", "value": f"#{rankings.get('reliability_rank')} of {rankings.get('peer_count')}" if rankings.get("reliability_rank") else "Pending"},
    ]
    faq_items = [
        {
            "question": f"Which DisCos serve {name}?",
            "answer": f"{name} is mapped to {disco_names} in Nigeria Power Data's planning-grade franchise coverage model.",
        },
        {
            "question": f"What does the {name} power availability estimate mean?",
            "answer": "Power availability compares estimated allocation against a peak-demand proxy derived from population, urbanization, industrial activity, and demand-growth assumptions.",
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
            "eyebrow": f"{scope_label} SEO Intelligence",
            "h1": title,
            "lede": description,
            "summary": payload.get("analysis_summary"),
            "facts": facts,
            "faq_items": faq_items,
            "breadcrumbs": breadcrumbs,
        },
    }


def _directory_faq(entity_label):
    return [
        {
            "question": f"What is the Nigeria Power Data {entity_label} directory?",
            "answer": f"It is a crawlable index of {entity_label} landing pages with live-linked historical trends, forecasts, rankings, and risk indicators from the platform.",
        },
        {
            "question": "How are these pages updated?",
            "answer": "Directory pages link to dynamic landing pages that update as the scheduler stores new public grid readings and analytics snapshots.",
        },
    ]


def _content_schema(page_slug, page):
    faq_items = None
    if page_slug in FAQ_CONTENT_PAGES:
        faq_items = [
            {"question": section["heading"], "answer": section["body"]}
            for section in page.get("sections", [])
        ]
    return _schema(
        page["title"],
        page["description"],
        f"/{page_slug}",
        [{"name": "Home", "path": "/"}, {"name": page["title"], "path": f"/{page_slug}"}],
        page_type="WebPage",
        article_type="Article",
        article_sections=[section["heading"] for section in page.get("sections", [])],
        faq_items=faq_items,
    )


def _article_schema(article, breadcrumbs):
    return _schema(
        article["title"],
        article["description"],
        article["url"],
        breadcrumbs,
        page_type="WebPage",
        article_type="Article",
        article_sections=[section["heading"] for section in article.get("sections", [])],
        article_date_published=article["published_at"],
        article_date_modified=article["updated_at"],
        article_keywords=article.get("keywords"),
        article_image_path=article.get("social_image") or article.get("image"),
        faq_items=article.get("faqs"),
    )


def _configured_content_page(page_slug):
    page = deepcopy(CONTENT_PAGES.get(page_slug))
    if not page:
        return None
    values = {
        "CONTACT_EMAIL": current_app.config["CONTACT_EMAIL"],
        "RESEARCH_EMAIL": current_app.config["RESEARCH_EMAIL"],
        "ADS_EMAIL": current_app.config["ADS_EMAIL"],
    }
    for key in ("title", "description", "eyebrow", "headline", "lede"):
        if isinstance(page.get(key), str):
            page[key] = page[key].format(**values)
    for section in page.get("sections", []):
        for key in ("heading", "body"):
            if isinstance(section.get(key), str):
                section[key] = section[key].format(**values)
    return page


@web_bp.get("/")
def index():
    description = "Nigeria Power Data tracks real-time generation, GenCo performance, DisCo allocation, grid health, and transformer loading intelligence for Nigeria's electricity market."
    title = "Nigeria Power Data | Real-Time Grid Intelligence"
    return render_template(
        "index.html",
        social_meta=_social(title, description, "/"),
        structured_data=_schema(
            "Nigeria Power Data | Grid & Distribution Intelligence",
            description,
            "/",
            [{"name": "Home", "path": "/"}],
        ),
    )


@web_bp.get("/discos/<slug>")
def disco_page(slug):
    seo = _entity_seo_context("disco", slug)
    return render_template(
        "entity.html",
        entity_type="disco",
        entity_plural="discos",
        slug=slug,
        canonical_path=seo["canonical_path"],
        page_title=seo["title"],
        entity_label="DisCo",
        description=seo["description"],
        seo_content=seo["content"],
        social_meta=_social(seo["title"], seo["description"], seo["canonical_path"], og_type="article"),
        structured_data=_report_schema(
            seo["title"],
            seo["description"],
            seo["canonical_path"],
            seo["breadcrumbs"],
            seo["sections"],
            faq_items=seo["faq_items"],
        ),
    )


@web_bp.get("/gencos/<slug>")
def genco_page(slug):
    seo = _entity_seo_context("genco", slug)
    return render_template(
        "entity.html",
        entity_type="genco",
        entity_plural="gencos",
        slug=slug,
        canonical_path=seo["canonical_path"],
        page_title=seo["title"],
        entity_label="GenCo",
        description=seo["description"],
        seo_content=seo["content"],
        social_meta=_social(seo["title"], seo["description"], seo["canonical_path"], og_type="article"),
        structured_data=_report_schema(
            seo["title"],
            seo["description"],
            seo["canonical_path"],
            seo["breadcrumbs"],
            seo["sections"],
            faq_items=seo["faq_items"],
        ),
    )


@web_bp.get("/discos")
def discos_directory_page():
    title = "Nigeria DisCo Intelligence Directory"
    description = "SEO index of Nigerian electricity distribution companies with allocation trends, transformer loading, settlement pressure, and risk intelligence."
    breadcrumbs = [{"name": "Home", "path": "/"}, {"name": "DisCos", "path": "/discos"}]
    faq_items = _directory_faq("DisCo")
    return render_template(
        "entity_index.html",
        title=title,
        description=description,
        canonical_path="/discos",
        entity_label="DisCo",
        entity_plural="discos",
        entities=list_entities("disco"),
        breadcrumbs=breadcrumbs,
        faq_items=faq_items,
        social_meta=_social(title, description, "/discos"),
        structured_data=_schema(
            title,
            description,
            "/discos",
            breadcrumbs,
            page_type="CollectionPage",
            article_type="Article",
            article_sections=["DisCo allocation", "Transformer loading", "Distribution risk"],
            faq_items=faq_items,
        ),
    )


@web_bp.get("/gencos")
def gencos_directory_page():
    title = "Nigeria GenCo Intelligence Directory"
    description = "SEO index of Nigerian generation companies and plants with output trends, forecasts, rankings, volatility, and performance intelligence."
    breadcrumbs = [{"name": "Home", "path": "/"}, {"name": "GenCos", "path": "/gencos"}]
    faq_items = _directory_faq("GenCo")
    return render_template(
        "entity_index.html",
        title=title,
        description=description,
        canonical_path="/gencos",
        entity_label="GenCo",
        entity_plural="gencos",
        entities=list_entities("genco"),
        breadcrumbs=breadcrumbs,
        faq_items=faq_items,
        social_meta=_social(title, description, "/gencos"),
        structured_data=_schema(
            title,
            description,
            "/gencos",
            breadcrumbs,
            page_type="CollectionPage",
            article_type="Article",
            article_sections=["GenCo output", "Generation history", "Performance ranking"],
            faq_items=faq_items,
        ),
    )


@web_bp.get("/states")
def states_page():
    title = "State Intelligence"
    description = "State and regional power allocation intelligence for Nigeria."
    return render_template(
        "geo_index.html",
        title=title,
        description=description,
        states=list_states(),
        regions=list_regions(),
        canonical_path="/states",
        social_meta=_social(title, description, "/states"),
        structured_data=_schema(
            title,
            description,
            "/states",
            [{"name": "Home", "path": "/"}, {"name": "States", "path": "/states"}],
        ),
    )


@web_bp.get("/regions")
def regions_page():
    title = "Regional Intelligence"
    description = "Regional power allocation, reliability, infrastructure stress, and DisCo coverage intelligence for Nigeria."
    return render_template(
        "geo_index.html",
        title=title,
        description=description,
        states=list_states(),
        regions=list_regions(),
        focus="regions",
        canonical_path="/regions",
        social_meta=_social(title, description, "/regions"),
        structured_data=_schema(
            title,
            description,
            "/regions",
            [{"name": "Home", "path": "/"}, {"name": "Regions", "path": "/regions"}],
        ),
    )


@web_bp.get("/geography")
def hierarchy_page():
    title = "Nigeria Geographic Power Intelligence Map"
    description = "Interactive Nigeria map with state, LGA, town, community, and settlement-level electricity demand intelligence."
    return render_template(
        "hierarchy_index.html",
        title=title,
        description=description,
        counts=hierarchy_counts(),
        social_meta=_social(title, description, "/geography"),
        structured_data=_schema(
            title,
            description,
            "/geography",
            [{"name": "Home", "path": "/"}, {"name": "Geography", "path": "/geography"}],
        ),
    )


@web_bp.get("/geography/<level>/<slug>")
def hierarchy_detail_page(level, slug):
    display_name = _display_slug(slug)
    title = f"{display_name} Geographic Drill-Down Intelligence"
    description = "Hierarchical power demand, transformer loading, DisCo coverage, grid health, and infrastructure upgrade intelligence."
    return render_template(
        "hierarchy_detail.html",
        level=level,
        slug=slug,
        page_title=title,
        description=description,
        social_meta=_social(title, description, f"/geography/{level}/{slug}", og_type="article"),
        structured_data=_report_schema(
            title,
            description,
            f"/geography/{level}/{slug}",
            [
                {"name": "Home", "path": "/"},
                {"name": "Geography", "path": "/geography"},
                {"name": display_name, "path": f"/geography/{level}/{slug}"},
            ],
            ["Demand projection", "Transformer loading", "Infrastructure upgrades"],
        ),
    )


@web_bp.get("/state/<slug>")
def state_page(slug):
    seo = _geo_seo_context("state", slug)
    return render_template(
        "geo.html",
        scope="state",
        api_collection="states",
        slug=slug,
        canonical_path=seo["canonical_path"],
        page_title=seo["title"],
        description=seo["description"],
        seo_content=seo["content"],
        related_articles=related_articles_for_context("state", slug),
        social_meta=_social(seo["title"], seo["description"], seo["canonical_path"], og_type="article"),
        structured_data=_report_schema(
            seo["title"],
            seo["description"],
            seo["canonical_path"],
            seo["breadcrumbs"],
            seo["sections"],
            faq_items=seo["faq_items"],
        ),
    )


@web_bp.get("/region/<slug>")
def region_page(slug):
    seo = _geo_seo_context("region", slug)
    return render_template(
        "geo.html",
        scope="region",
        api_collection="regions",
        slug=slug,
        canonical_path=seo["canonical_path"],
        page_title=seo["title"],
        description=seo["description"],
        seo_content=seo["content"],
        related_articles=related_articles_for_context("region", slug),
        social_meta=_social(seo["title"], seo["description"], seo["canonical_path"], og_type="article"),
        structured_data=_report_schema(
            seo["title"],
            seo["description"],
            seo["canonical_path"],
            seo["breadcrumbs"],
            seo["sections"],
            faq_items=seo["faq_items"],
        ),
    )


@web_bp.get("/articles")
def articles_page():
    query = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    page_number = request.args.get("page", 1, type=int) or 1
    listing = search_articles(query=query, category=category, page=page_number)
    featured = featured_article()
    title = "Nigeria Power Data Articles"
    description = (
        "Original explainers and research guides on Nigeria's power grid, generation, "
        "distribution, transmission, market structure, and electricity data."
    )
    breadcrumbs = [{"name": "Home", "path": "/"}, {"name": "Articles", "path": "/articles"}]
    return render_template(
        "articles.html",
        title=title,
        description=description,
        canonical_path="/articles",
        query=query,
        category=category,
        listing=listing,
        categories=article_categories(),
        featured=featured,
        latest=latest_articles(4),
        popular=popular_articles(5),
        topics=related_topics(),
        breadcrumbs=breadcrumbs,
        social_meta=_social(
            title,
            description,
            "/articles",
            image_path=featured.get("social_image") or featured.get("image"),
            image_alt=featured.get("image_alt"),
        ),
        structured_data=_schema(
            title,
            description,
            "/articles",
            breadcrumbs,
            page_type="CollectionPage",
            article_sections=["Grid operations", "Generation", "Distribution", "Market", "Policy"],
        ),
    )


@web_bp.get("/articles/<slug>")
def article_page(slug):
    article = get_article(slug)
    if not article:
        abort(404)
    previous_article, next_article = adjacent_articles(slug)
    breadcrumbs = [
        {"name": "Home", "path": "/"},
        {"name": "Articles", "path": "/articles"},
        {"name": article["title"], "path": article["url"]},
    ]
    return render_template(
        "article.html",
        article=article,
        canonical_path=article["url"],
        related_articles=related_articles(article),
        previous_article=previous_article,
        next_article=next_article,
        breadcrumbs=breadcrumbs,
        social_meta=_social(
            article["title"],
            article["description"],
            article["url"],
            image_path=article.get("social_image") or article.get("image"),
            image_alt=article.get("image_alt"),
            og_type="article",
            published_time=article["published_at"],
            modified_time=article["updated_at"],
        ),
        structured_data=_article_schema(article, breadcrumbs),
    )


@web_bp.get("/<page_slug>")
def content_page(page_slug):
    page = _configured_content_page(page_slug)
    if not page:
        abort(404)
    return render_template(
        "page.html",
        page=page,
        page_slug=page_slug,
        social_meta=_social(page["title"], page["description"], f"/{page_slug}", og_type="article"),
        structured_data=_content_schema(page_slug, page),
    )


@web_bp.get("/robots.txt")
def robots():
    sitemap_url = f"{current_app.config['APP_BASE_URL']}/sitemap.xml"
    body = "\n".join(
        [
            "# Nigeria Power Data robots.txt",
            "# Public dashboards, content pages, static assets, sitemap, and IndexNow key files are crawlable by default.",
            "# Do not use robots.txt for security; private systems must still require authentication.",
            "# Major search engines and default compliant crawlers share one crawl policy.",
            "# Only private, administrative, health, and internal JSON endpoints are disallowed.",
            "User-agent: Googlebot",
            "User-agent: Googlebot-Image",
            "User-agent: Bingbot",
            "User-agent: DuckDuckBot",
            "User-agent: Applebot",
            "User-agent: YandexBot",
            "User-agent: Baiduspider",
            "User-agent: *",
            "Disallow: /admin",
            "Disallow: /admin/",
            "Disallow: /internal",
            "Disallow: /internal/",
            "Disallow: /private",
            "Disallow: /private/",
            "Disallow: /login",
            "Disallow: /logout",
            "Disallow: /api/health",
            "Disallow: /api/indexnow",
            "Disallow: /api/grid/",
            "Disallow: /api/latest",
            "Disallow: /api/history",
            "Disallow: /api/analytics",
            "Disallow: /api/market-data",
            "Disallow: /api/generation",
            "Disallow: /api/entities",
            "Disallow: /api/discos",
            "Disallow: /api/gencos",
            "Disallow: /api/states",
            "Disallow: /api/regions",
            "Disallow: /api/geography",
            "Allow: /static/",
            "Allow: /sitemap.xml",
            "Allow: /robots.txt",
            "Allow: /api/metadata",
            "Allow: /api/distribution",
            "",
            "# Sitemap location for Google Search Console, Bing Webmaster Tools, and other crawlers.",
            f"Sitemap: {sitemap_url}",
            "",
        ]
    )
    return Response(body, mimetype="text/plain")


@web_bp.get("/sitemap.xml")
def sitemap():
    url_entries = "\n".join(
        f"""  <url>
    <loc>{entry['loc']}</loc>
    <changefreq>{entry['changefreq']}</changefreq>
    <priority>{entry['priority']}</priority>
  </url>"""
        for entry in public_url_entries(current_app.config["APP_BASE_URL"])
    )
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{url_entries}
</urlset>
"""
    return Response(body, mimetype="application/xml")


@web_bp.get("/<key_file>.txt")
def indexnow_key_file(key_file):
    if key_file != indexnow_key():
        abort(404)
    return Response(indexnow_key_file_body(), mimetype="text/plain; charset=utf-8")


@web_bp.get("/favicon.svg")
def favicon():
    return send_from_directory(current_app.static_folder, "favicon.svg", mimetype="image/svg+xml")
