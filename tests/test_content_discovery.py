"""Educational resources must stay discoverable without becoming research papers."""
from datetime import date, datetime, timezone
import json
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import pytest

from grid_monitor.services.articles import ARTICLES, search_articles
from tools.research_data_audit import audit_readings


def soup(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    return BeautifulSoup(response.data, "html.parser")


def graphs(page):
    return [node for script in page.select('script[type="application/ld+json"]')
            for node in json.loads(script.string)["@graph"]]


@pytest.fixture(autouse=True)
def empty_catalog(app, tmp_path):
    app.config["RESEARCH_CONTENT_DIR"] = str(tmp_path)


def test_all_ten_guides_discoverable_without_research(client):
    page = soup(client, "/research")
    assert len(ARTICLES) == 10
    assert page.select_one("#research-publications")
    assert "No research publications yet" in page.select_one("#research-publications").get_text()
    assert not page.select("#research-publications .research-guide-card")
    guides = page.select("#energy-guides .research-guide-link")
    assert {link["href"] for link in guides} == {article["url"] for article in ARTICLES}
    assert "Related Energy Articles & Guides" in page.get_text()
    assert not page.select('meta[name^="citation_"]')
    assert not any(node["@type"] in {"ScholarlyArticle", "Article"} for node in graphs(page))
    for image in page.select("#energy-guides img"):
        assert image["alt"].strip()
        assert image["width"] == "1280" and image["height"] == "720"
        assert image["loading"] == "lazy"


@pytest.mark.parametrize("query,expected", [
    ("electricity", "how-electricity-is-generated-in-nigeria"),
    ("grid", "understanding-nigerias-national-grid"),
    ("distribution", "electricity-distribution-in-nigeria"),
])
def test_shared_search_finds_educational_resources(client, query, expected):
    page = soup(client, f"/research?q={query}")
    assert page.select_one(f'#energy-guides a[href="/articles/{expected}"]')
    assert "No research publications yet" in page.select_one("#research-publications").get_text()
    assert page.select_one('meta[name="robots"]')["content"] == "noindex, follow"
    assert page.select_one('link[rel="canonical"]')["href"].endswith("/research")
    assert {a["href"] for a in page.select("#energy-guides .research-guide-link")} == {
        a["url"] for a in search_articles(query=query, per_page=12)["articles"]
    }


def test_publication_type_filter_does_not_misclassify_or_hide_guides(client):
    page = soup(client, "/research?type=technical-report&q=distribution")
    assert page.select("#energy-guides .research-guide-card")
    assert page.select_one("#energy-guides .research-guide-link")["href"] == "/articles/electricity-distribution-in-nigeria"
    assert "No research publications yet" in page.select_one("#research-publications").get_text()
    assert not page.select("#research-publications .research-list-item")
    empty = soup(client, "/research?q=nonexistentzzzz")
    assert "No educational guides match" in empty.get_text()
    assert client.get("/research/understanding-nigerias-national-grid").status_code == 404


@pytest.mark.parametrize("article", ARTICLES, ids=lambda item: item["slug"])
def test_each_article_metadata_attribution_and_accessibility(client, app, article):
    page = soup(client, article["url"])
    canonical = app.config["APP_BASE_URL"].rstrip("/") + article["url"]
    assert len(page.select('link[rel="canonical"]')) == 1
    assert page.select_one('link[rel="canonical"]')["href"] == canonical
    assert page.title.get_text() == article["title"] + " | Nigeria Power Data"
    assert page.select_one('meta[name="description"]')["content"] == article["description"]
    assert page.select_one('meta[name="keywords"]')["content"] == ", ".join(article["keywords"])
    assert page.select_one('meta[name="author"]')["content"] == article["author"]
    assert page.select_one('meta[name="robots"]')["content"] == "index, follow"
    assert page.select_one('meta[name="viewport"]')
    assert len(page.select("h1")) == 1
    assert not page.select("[itemscope]")  # One JSON-LD representation, no duplicate Article microdata.
    assert not page.select('meta[name^="citation_"]')
    assert len(page.select('script[type="application/ld+json"]')) == 1
    nodes = graphs(page)
    articles = [node for node in nodes if node["@type"] == "Article"]
    assert len(articles) == 1
    assert not any(node["@type"] == "ScholarlyArticle" for node in nodes)
    node = articles[0]
    assert node["author"]["name"] == article["author"] == "Nigeria Power Data Team"
    assert node["author"]["@type"] == "Organization"
    assert node["author"]["url"].endswith("/about")
    assert node["datePublished"] == article["published_at"]
    assert node["dateModified"] == article["updated_at"]
    assert node["datePublished"] == "2026-07-15"
    assert node["dateModified"] == "2026-07-15"
    assert date.fromisoformat(node["dateModified"]) <= date.today()
    assert len(node["citation"]) == len(article["references"])
    assert page.select(f'time[datetime="{article["published_at"]}"]')
    assert len(page.select('meta[property="og:title"]')) == 1
    assert page.select_one('meta[property="og:url"]')["content"] == canonical
    assert page.select_one('meta[property="og:image"]')["content"] == article["social_image"]
    assert page.select_one('meta[name="twitter:image"]')["content"] == article["social_image"]
    assert page.select_one('meta[property="article:published_time"]')["content"] == article["published_at"]
    assert page.select_one('meta[property="article:modified_time"]')["content"] == article["updated_at"]
    assert page.select_one('a[href="/research"]')
    assert page.select_one('a[href="/methodology"]')
    assert page.select_one('a[href="/data-sources"]')
    assert len(page.select("#references li")) == len(article["references"])
    for image in page.select("img"):
        assert image.get("alt")
        assert image.get("width") and image.get("height")
    for table in page.select("table.article-table"):
        assert table.find("caption")
        assert table.parent.get("tabindex") == "0"
        assert all(th.get("scope") == "col" for th in table.select("thead th"))


def test_unique_metadata_and_stable_sitemap_entries(client, app):
    assert len({a["title"] for a in ARTICLES}) == 10
    assert len({a["description"] for a in ARTICLES}) == 10
    assert len({a["url"] for a in ARTICLES}) == 10
    xml = ET.fromstring(client.get("/sitemap.xml").data)
    entries = [node.text for node in xml.findall("{*}url/{*}loc")]
    robots = RobotFileParser()
    robots.parse(client.get("/robots.txt").get_data(as_text=True).splitlines())
    base = app.config["APP_BASE_URL"].rstrip("/")
    for path in ["/research", "/articles", "/methodology", "/data-sources", *(a["url"] for a in ARTICLES)]:
        assert entries.count(base + path) == 1
        for agent in ("Googlebot", "Bingbot"):
            assert robots.can_fetch(agent, base + path)
    assert not any("/research/" in entry for entry in entries)
    assert not any("/docs/research" in entry for entry in entries)


def test_contextual_links_and_existing_services(client):
    for path in ("/methodology", "/data-sources"):
        page = soup(client, path)
        assert page.select_one('#further-reading a[href="/research"]')
        assert page.select_one('#further-reading a[href="/articles/reading-nigeria-power-data-dashboard"]')
    for article in ARTICLES:
        for link in article["internal_links"]:
            assert client.get(urlsplit(link["url"]).path or "/").status_code == 200
    for path in ("/", "/states", "/state/lagos", "/state/edo", "/region/north-central", "/api/health"):
        assert client.get(path).status_code == 200
    for path in ("/", "/articles", "/research"):
        page = client.get(path).get_data(as_text=True)
        assert "G-DT9LWGETK7" in page
        assert "xg7x92w5gh" in page


def test_quality_audit_identifies_gaps_without_inventing_outages():
    rows = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "captured_at": "2026-01-01T00:01:00+00:00", "total_generation_mw": 100},
        {"timestamp": "2026-01-01T02:00:00+00:00", "captured_at": "2026-01-01T02:01:00+00:00", "total_generation_mw": 0},
        {"timestamp": "2026-01-01T02:00:00+00:00", "captured_at": None, "total_generation_mw": None},
        {"timestamp": "2026-01-01T03:00:00", "captured_at": None, "total_generation_mw": float("nan")},
    ]
    audit = audit_readings(rows, expected_interval_seconds=1800,
                           now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert audit["counts"]["rows"] == 4
    assert audit["counts"]["gaps_over_1_5_expected_intervals"] == 1
    assert audit["counts"]["adjacent_duplicate_timestamps"] == 1
    assert audit["counts"]["zero_generation_review_required"] == 1
    assert audit["counts"]["missing_or_nonfinite_generation"] == 2
    assert audit["counts"]["invalid_or_timezone_missing_timestamp"] == 1
    assert "not confirmed outages" in audit["interpretation"]
    assert "findings" not in audit


def test_quality_audit_flags_history_fallback_outside_window():
    audit = audit_readings(
        [{"timestamp": "2026-01-01T00:00:00+00:00", "total_generation_mw": 100}],
        expected_interval_seconds=1800,
        since=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    assert audit["counts"]["outside_requested_window"] == 1


def test_database_quality_audit_does_not_modify_source(tmp_path, monkeypatch):
    import sqlite3
    from tools.research_data_audit import database_audit

    database = tmp_path / "audit.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE grid_snapshots(reading_timestamp TEXT, captured_at TEXT, total_generation_mw REAL, source TEXT, source_url TEXT);"
            "INSERT INTO grid_snapshots VALUES('2026-01-01 00:00:00', '2026-01-01 00:01:00', 100, 'synthetic', 'https://example.org');"
            "CREATE TABLE genco_data(snapshot_id INTEGER, plant TEXT, generation_mw REAL);"
            "CREATE TABLE disco_data(snapshot_id INTEGER, company TEXT, load_allocation_mw REAL);"
        )
    original = database.read_bytes()
    monkeypatch.setenv("RESEARCH_DATABASE_URL", f"sqlite:///{database}")
    report = database_audit(expected_interval_seconds=1800)
    assert report["counts"]["rows"] == 1
    assert report["research_calculations_performed"] is False
    assert report["data_reuse_rights"] == "unverified"
    assert database.read_bytes() == original


def test_article_pagination_and_search_indexing(client):
    first = soup(client, "/articles")
    second = soup(client, "/articles?page=2")
    assert first.select_one('link[rel="canonical"]')["href"].endswith("/articles")
    assert second.select_one('link[rel="canonical"]')["href"].endswith("/articles?page=2")
    assert second.select_one('meta[property="og:url"]')["content"].endswith("/articles?page=2")
    assert "Page 2" in second.title.get_text()
    assert second.select_one('meta[name="robots"]')["content"] == "index, follow"
    for query in ("?q=grid", "?category=Distribution"):
        page = soup(client, "/articles" + query)
        assert page.select_one('meta[name="robots"]')["content"] == "noindex, follow"
        assert page.select_one('link[rel="canonical"]')["href"].endswith("/articles")
