from flask import Blueprint, Response, abort, current_app, render_template, send_from_directory


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
                "body": "Email: hello@nigeriapowerdata.com. Include the page URL, timestamp, and source reading if you are reporting a data issue.",
            },
            {
                "heading": "Data Corrections",
                "body": "Because the dashboard depends on public source data, corrections should reference the original NISO/NIGGRID publication where possible.",
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
                "heading": "Data Freshness",
                "body": "Stored readings are collected on the configured scheduler interval. Public source downtime, layout changes, or deployment sleep can affect freshness.",
            },
        ],
    },
}


@web_bp.get("/")
def index():
    return render_template("index.html")


@web_bp.get("/discos/<slug>")
def disco_page(slug):
    return render_template(
        "entity.html",
        entity_type="disco",
        entity_plural="discos",
        slug=slug,
        page_title="DisCo Intelligence",
        entity_label="DisCo",
        description="DisCo load allocation, transformer utilization, risk, forecast, and settlement growth intelligence.",
    )


@web_bp.get("/gencos/<slug>")
def genco_page(slug):
    return render_template(
        "entity.html",
        entity_type="genco",
        entity_plural="gencos",
        slug=slug,
        page_title="GenCo Intelligence",
        entity_label="GenCo",
        description="GenCo output history, forecast, volatility, ranking, and performance intelligence.",
    )


@web_bp.get("/<page_slug>")
def content_page(page_slug):
    page = CONTENT_PAGES.get(page_slug)
    if not page:
        abort(404)
    return render_template("page.html", page=page, page_slug=page_slug)


@web_bp.get("/robots.txt")
def robots():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {current_app.config['APP_BASE_URL']}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")


@web_bp.get("/sitemap.xml")
def sitemap():
    base_url = current_app.config["APP_BASE_URL"]
    pages = ["about", "contact", "privacy-policy", "terms-of-use", "methodology", "data-sources"]
    page_urls = "\n".join(
        f"""  <url>
    <loc>{base_url}/{page}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>"""
        for page in pages
    )
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/</loc>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
{page_urls}
  <url>
    <loc>{base_url}/api/metadata</loc>
    <changefreq>daily</changefreq>
    <priority>0.4</priority>
  </url>
  <url>
    <loc>{base_url}/api/distribution</loc>
    <changefreq>hourly</changefreq>
    <priority>0.5</priority>
  </url>
</urlset>
"""
    return Response(body, mimetype="application/xml")


@web_bp.get("/favicon.svg")
def favicon():
    return send_from_directory(current_app.static_folder, "favicon.svg", mimetype="image/svg+xml")
