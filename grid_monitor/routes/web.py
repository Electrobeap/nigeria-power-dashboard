from copy import deepcopy

from flask import Blueprint, Response, abort, current_app, render_template, send_from_directory

from grid_monitor.services.indexnow import indexnow_key, indexnow_key_file_body
from grid_monitor.services.geographic_hierarchy import hierarchy_counts
from grid_monitor.services.site_urls import public_url_entries
from grid_monitor.services.social_meta import build_social_meta
from grid_monitor.services.state_intelligence import list_regions, list_states
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


def _schema(title, description, path, breadcrumbs, **kwargs):
    return build_structured_data(
        title=title,
        description=description,
        path=path,
        breadcrumbs=breadcrumbs,
        **kwargs,
    )


def _social(title, description, path, og_type="website"):
    return build_social_meta(
        title=title,
        description=description,
        path=path,
        og_type=og_type,
    )


def _report_schema(title, description, path, breadcrumbs, sections):
    return _schema(
        title,
        description,
        path,
        breadcrumbs,
        page_type="WebPage",
        article_type="Article",
        article_sections=sections,
    )


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
    display_name = _display_slug(slug)
    title = f"{display_name} DisCo Intelligence"
    description = "DisCo load allocation, transformer utilization, risk, forecast, and settlement growth intelligence."
    return render_template(
        "entity.html",
        entity_type="disco",
        entity_plural="discos",
        slug=slug,
        page_title=title,
        entity_label="DisCo",
        description=description,
        social_meta=_social(title, description, f"/discos/{slug}", og_type="article"),
        structured_data=_report_schema(
            title,
            description,
            f"/discos/{slug}",
            [
                {"name": "Home", "path": "/"},
                {"name": "DisCo Intelligence", "path": "/#distribution"},
                {"name": display_name, "path": f"/discos/{slug}"},
            ],
            ["DisCo allocation", "Transformer utilization", "Forecast and risk"],
        ),
    )


@web_bp.get("/gencos/<slug>")
def genco_page(slug):
    display_name = _display_slug(slug)
    title = f"{display_name} GenCo Intelligence"
    description = "GenCo output history, forecast, volatility, ranking, and performance intelligence."
    return render_template(
        "entity.html",
        entity_type="genco",
        entity_plural="gencos",
        slug=slug,
        page_title=title,
        entity_label="GenCo",
        description=description,
        social_meta=_social(title, description, f"/gencos/{slug}", og_type="article"),
        structured_data=_report_schema(
            title,
            description,
            f"/gencos/{slug}",
            [
                {"name": "Home", "path": "/"},
                {"name": "GenCo Performance", "path": "/#market-data"},
                {"name": display_name, "path": f"/gencos/{slug}"},
            ],
            ["GenCo output", "Performance ranking", "Forecast and volatility"],
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
    display_name = _display_slug(slug)
    title = f"{display_name} State Intelligence"
    description = "State power allocation, demand, reliability, transformer risk, and regional electricity intelligence."
    return render_template(
        "geo.html",
        scope="state",
        api_collection="states",
        slug=slug,
        page_title=title,
        description=description,
        social_meta=_social(title, description, f"/state/{slug}", og_type="article"),
        structured_data=_report_schema(
            title,
            description,
            f"/state/{slug}",
            [
                {"name": "Home", "path": "/"},
                {"name": "States", "path": "/states"},
                {"name": display_name, "path": f"/state/{slug}"},
            ],
            ["State allocation", "Demand growth", "Reliability and transformer risk"],
        ),
    )


@web_bp.get("/region/<slug>")
def region_page(slug):
    display_name = _display_slug(slug)
    title = f"{display_name} Regional Intelligence"
    description = "Regional power allocation, state coverage, infrastructure stress, demand growth, and grid reliability intelligence."
    return render_template(
        "geo.html",
        scope="region",
        api_collection="regions",
        slug=slug,
        page_title=title,
        description=description,
        social_meta=_social(title, description, f"/region/{slug}", og_type="article"),
        structured_data=_report_schema(
            title,
            description,
            f"/region/{slug}",
            [
                {"name": "Home", "path": "/"},
                {"name": "Regions", "path": "/regions"},
                {"name": display_name, "path": f"/region/{slug}"},
            ],
            ["Regional allocation", "Infrastructure stress", "Demand growth"],
        ),
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
