"""Synthetic records below are test fixtures, never deployed research content."""
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
import json
from pathlib import Path
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from pypdf import PdfReader
import pytest

from grid_monitor.services.research import (
    ResearchValidationError, _cached_records, bibtex, list_publications,
    normalize_orcid, read_records, validate_record,
)
from tools.research_publications import build_pdf, validate_pdf


@pytest.fixture()
def record():
    return {
        "slug": "synthetic-validation-study-v1",
        "title": "Synthetic publication for automated validation",
        "status": "published", "publication_type": "technical-report",
        "version": "1.0", "published_at": "2026-01-01", "updated_at": "2026-01-02",
        "authors": [
            {"given_name": "First Test", "family_name": "Author", "affiliations": ["Synthetic Test Institution"]},
            {"given_name": "Second Test", "family_name": "Author", "affiliations": []},
        ],
        "abstract": "This synthetic fixture tests metadata consistency. It makes no claims about electricity conditions.",
        "keywords": ["test fixture", "metadata"],
        "methodology": ["Compare output to a synthetic record."],
        "findings": ["No empirical research findings are asserted by this fixture."],
        "limitations": ["This is software test data only."],
        "assumptions": ["The supplied record is synthetic."],
        "references": [{"citation": "Synthetic software validation reference.", "url": "https://example.org/reference"}],
        "data_provenance": [{
            "citation": "Synthetic source", "url": "https://example.org/data",
            "data_kind": "estimated", "accessed_on": "2026-01-01",
            "coverage": "Synthetic test window", "processing": "No actual measurements",
            "license": "Test fixture only",
        }],
        "license": "Test fixture only", "peer_review_status": "not_peer_reviewed",
        "publication_approved": True, "rights_confirmed": True,
        "pdf_file": "papers/synthetic-validation-study-v1.pdf",
        "pdf_publication_approved": True,
    }


@pytest.fixture()
def catalog(app, tmp_path, record):
    app.config["RESEARCH_CONTENT_DIR"] = str(tmp_path)
    build_pdf(record, tmp_path)
    (tmp_path / f'{record["slug"]}.json').write_text(json.dumps(record), encoding="utf-8")
    _cached_records.cache_clear()
    yield tmp_path
    _cached_records.cache_clear()


def html(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return BeautifulSoup(response.data, "html.parser")


def test_library_empty_does_not_invent_research(app, client, tmp_path):
    app.config["RESEARCH_CONTENT_DIR"] = str(tmp_path)
    page = html(client, "/research")
    assert "No research publications yet" in page.get_text()
    assert not page.select('meta[name="citation_title"]')
    assert not page.select(".research-list-item")
    assert client.get("/research/nonexistent").status_code == 404


def test_metadata_attribution_and_graph_match_record(app, client, catalog, record):
    page = html(client, f'/research/{record["slug"]}')
    base = app.config["APP_BASE_URL"].rstrip("/")
    canonical = f'{base}/research/{record["slug"]}'
    assert page.find("meta", attrs={"name": "citation_title"})["content"] == record["title"]
    assert [tag["content"] for tag in page.select('meta[name="citation_author"]')] == ["First Test Author", "Second Test Author"]
    assert page.select_one('meta[name="citation_publication_date"]')["content"] == "2026/01/01"
    assert page.select_one('meta[name="citation_pdf_url"]')["content"] == canonical + "/paper.pdf"
    assert len(page.select('link[rel="canonical"]')) == 1
    assert page.select_one('link[rel="canonical"]')["href"] == canonical
    assert len(page.select('meta[property="og:title"]')) == 1
    assert len(page.select('meta[name="twitter:title"]')) == 1
    assert record["abstract"] in page.select_one(".research-abstract").get_text()
    scripts = page.select('script[type="application/ld+json"]')
    assert len(scripts) == 1
    graph = json.loads(scripts[0].string)["@graph"]
    scholarly = [node for node in graph if node["@type"] == "ScholarlyArticle"]
    assert len(scholarly) == 1
    node = scholarly[0]
    assert node["isAccessibleForFree"] is True
    assert node["datePublished"] == record["published_at"]
    assert node["version"] == "1.0"
    assert node["abstract"] == record["abstract"]
    assert [author["name"] for author in node["author"]] == ["First Test Author", "Second Test Author"]
    assert all(author["@type"] == "Person" for author in node["author"])
    assert node["author"][0]["affiliation"][0]["name"] == "Synthetic Test Institution"
    assert "affiliation" not in node["author"][1]
    assert node["encoding"]["contentUrl"] == canonical + "/paper.pdf"
    assert not any(n["@type"] in {"Article", "NewsArticle", "Dataset"} for n in graph)
    assert "identifier" not in node
    assert "Not peer reviewed" in page.get_text()
    assert "googletagmanager.com/gtag/js?id=G-DT9LWGETK7" in str(page)
    assert "xg7x92w5gh" in str(page)


def test_pdf_searchable_and_matches_authors(client, catalog, record):
    response = client.get(f'/research/{record["slug"]}/paper.pdf')
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF-")
    assert response.headers["X-Robots-Tag"] == "index, follow"
    assert 'rel="canonical"' in response.headers["Link"]
    text = " ".join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
    assert "First Test Author" in text
    assert "Second Test Author" in text
    assert "References" in text
    validate_pdf(validate_record(record, catalog), catalog)


def test_sitemap_discovery_indexnow_and_robots(app, client, catalog, record):
    from grid_monitor.services.site_urls import public_urls
    base = app.config["APP_BASE_URL"].rstrip("/")
    document = ET.fromstring(client.get("/sitemap.xml").data)
    locations = [item.text for item in document.findall("{*}url/{*}loc")]
    assert base + "/research" in locations
    assert base + "/research/" + record["slug"] in locations
    with app.app_context():
        assert base + "/research/" + record["slug"] in public_urls(base)
    robots = RobotFileParser()
    robots.parse(client.get("/robots.txt").get_data(as_text=True).splitlines())
    for agent in ("Googlebot", "Bingbot", "*"):
        assert robots.can_fetch(agent, base + "/research")
        assert robots.can_fetch(agent, base + "/research/" + record["slug"])
        assert robots.can_fetch(agent, base + "/research/" + record["slug"] + "/paper.pdf")
    assert base + "/articles" in locations


def test_draft_future_and_missing_papers_are_never_public(app, client, catalog, record):
    path = catalog / f'{record["slug"]}.json'
    for updates in (
        {"status": "draft"},
        {"published_at": (date.today() + timedelta(days=2)).isoformat(),
         "updated_at": (date.today() + timedelta(days=2)).isoformat()},
        {"pdf_file": "papers/missing.pdf"},
        {"publication_approved": False},
    ):
        candidate = {**record, **updates}
        path.write_text(json.dumps(candidate), encoding="utf-8")
        _cached_records.cache_clear()
        for suffix in ("", "/paper.pdf", "/citation.bib", "/submission.json"):
            assert client.get(f'/research/{record["slug"]}{suffix}').status_code == 404
        assert record["slug"] not in client.get("/sitemap.xml").get_data(as_text=True)


def test_missing_pdf_invalidates_cache(app, client, catalog, record):
    assert client.get(f'/research/{record["slug"]}').status_code == 200
    (catalog / record["pdf_file"]).unlink()
    assert client.get(f'/research/{record["slug"]}').status_code == 404


def test_abstract_only_publication_has_no_pdf_claims(client, catalog, record):
    record.pop("pdf_file")
    (catalog / f'{record["slug"]}.json').write_text(json.dumps(record), encoding="utf-8")
    page = html(client, f'/research/{record["slug"]}')
    assert not page.select('meta[name="citation_pdf_url"]')
    graph = json.loads(page.select_one('script[type="application/ld+json"]').string)["@graph"]
    assert "encoding" not in next(node for node in graph if node["@type"] == "ScholarlyArticle")
    assert client.get(f'/research/{record["slug"]}/paper.pdf').status_code == 404


def test_search_filter_and_manual_exports(client, catalog, record):
    assert record["title"] in html(client, "/research?q=First+Test&type=technical-report").get_text()
    page = html(client, "/research?q=absent")
    assert "No matching publications" in page.get_text()
    assert page.select_one('meta[name="robots"]')["content"] == "noindex, follow"
    assert client.get("/research?type=unknown").status_code == 404
    response = client.get(f'/research/{record["slug"]}/citation.bib')
    assert response.status_code == 200
    assert "Author, First Test and Author, Second Test" in response.get_data(as_text=True)
    assert "doi =" not in response.get_data(as_text=True)
    export = client.get(f'/research/{record["slug"]}/submission.json')
    assert export.json["submission_method"] == "manual"
    assert export.json["doi"] is None
    assert export.headers["X-Robots-Tag"] == "noindex, follow"
    assert len(export.json["authors"]) == 2


@pytest.mark.parametrize("updates", [
    {"authors": []}, {"authors": [{"given_name": "Nigeria Power", "family_name": "Data Team"}]},
    {"methodology": []}, {"findings": []}, {"references": []}, {"data_provenance": []},
    {"peer_review_status": "externally_peer_reviewed"},
    {"doi": "10.5281/zenodo.0"},
    {"doi": "fabricated-identifier"},
    {"pdf_file": "../private.pdf"}, {"pdf_file": "papers/../../private.pdf"},
    {"rights_confirmed": False},
])
def test_reject_invalid_attribution_content_and_identifiers(record, tmp_path, updates):
    with pytest.raises(ResearchValidationError):
        validate_record({**record, **updates}, tmp_path, check_pdf=False)


def test_orcid_checksum():
    # ORCID's published example identifier; never attached to fixture authors.
    assert normalize_orcid("0000-0002-1825-0097") == "https://orcid.org/0000-0002-1825-0097"
    with pytest.raises(ResearchValidationError):
        normalize_orcid("0000-0002-1825-0098")


def test_registered_doi_is_explicit_input_only(record, tmp_path):
    # Intentionally synthetic DOI used only to test serialization, not registration.
    candidate = {**record, "doi": "10.5281/zenodo.0",
                 "doi_registration_confirmed": True, "doi_verified_on": "2026-01-02",
                 "doi_registration_url": "https://example.org/test-only-doi-evidence"}
    parsed = validate_record(candidate, tmp_path, check_pdf=False)
    assert "doi = {10.5281/zenodo.0}" in bibtex(parsed, "https://example.org")
    candidate["doi_registration_confirmed"] = False
    with pytest.raises(ResearchValidationError):
        validate_record(candidate, tmp_path, check_pdf=False)


def test_unsafe_source_urls_and_html_are_handled(client, catalog, record):
    invalid = deepcopy(record)
    invalid["data_provenance"][0]["url"] = "javascript:alert(1)"
    with pytest.raises(ResearchValidationError):
        validate_record(invalid, catalog)
    record["abstract"] = '<script>alert("test")</script> & a synthetic abstract.'
    # Avoid rebuilding fixture PDF: abstract-only records are also supported.
    record.pop("pdf_file")
    (catalog / f'{record["slug"]}.json').write_text(json.dumps(record), encoding="utf-8")
    page = html(client, f'/research/{record["slug"]}')
    assert not page.select_one(".research-abstract").find("script")
    assert record["abstract"] in page.select_one(".research-abstract").get_text()


def test_invalid_catalog_cannot_break_existing_pages(app, client, catalog):
    (catalog / "bad.json").write_text("{invalid", encoding="utf-8")
    assert client.get("/research").status_code == 200
    assert client.get("/articles").status_code == 200
    assert client.get("/sitemap.xml").status_code == 200
    with pytest.raises(ResearchValidationError):
        read_records(catalog, strict=True)


def test_original_articles_not_reclassified(client, catalog):
    page = html(client, "/articles")
    article_links = [a["href"] for a in page.select('a[href^="/articles/"]')]
    assert article_links
    article = html(client, article_links[0])
    assert not article.select('meta[name="citation_title"]')
    assert '"ScholarlyArticle"' not in str(article)
    assert page.select_one('a[href="/research"]')


def test_pdf_validation_rejects_mismatched_title(catalog, record):
    record["title"] = "Different title"
    with pytest.raises(ResearchValidationError):
        validate_pdf(validate_record(record, catalog), catalog)


def test_repository_catalog_is_ready_for_publication():
    from grid_monitor.services.research import DEFAULT_DIRECTORY
    for item in read_records(DEFAULT_DIRECTORY, strict=True):
        validate_pdf(item, DEFAULT_DIRECTORY)


# All repository IDs/evidence below are synthetic serialization fixtures.
# They are never added to the production catalog or claimed as actual listings.
@pytest.fixture()
def repository_record():
    return {
        "repository": "zenodo", "status": "published", "identifier": "0",
        "url": "https://zenodo.org/records/0",
        "verification": {
            "checked_on": "2026-01-02", "checked_by": "Synthetic test reviewer",
            "evidence_url": "https://example.org/test-only-record-evidence",
            "title_matches": True, "authors_match": True,
            "version_matches": True, "publicly_accessible": True,
        },
        "notes": "EDITORIAL-NOTE-NOT-FOR-PUBLIC-OUTPUT",
    }


def write_record(catalog, record):
    (catalog / f'{record["slug"]}.json').write_text(json.dumps(record), encoding="utf-8")
    _cached_records.cache_clear()


@pytest.mark.parametrize("entries", [
    [],
    [{"repository": "zenodo", "status": "not_submitted"}],
    [{"repository": "researchgate", "status": "pending", "submitted_on": "2026-01-01"}],
])
def test_repository_section_absent_without_confirmed_records(client, catalog, record, entries):
    record["repository_records"] = entries
    # Derived fields must not be accepted from unvalidated configuration.
    record["external_links"] = [{"url": "https://example.org/forged-link"}]
    write_record(catalog, record)
    page = html(client, f'/research/{record["slug"]}')
    assert not page.select_one("#also-available")
    assert "forged-link" not in str(page)
    data = client.get(f'/research/{record["slug"]}/submission.json').json
    assert data["external_publications"] == []
    graph = json.loads(page.select_one('script[type="application/ld+json"]').string)["@graph"]
    scholarly = next(item for item in graph if item["@type"] == "ScholarlyArticle")
    assert "sameAs" not in scholarly
    assert "identifier" not in scholarly


def test_verified_repository_links_schema_and_exports(app, client, catalog, record, repository_record):
    researchgate = deepcopy(repository_record)
    researchgate.update(repository="researchgate", identifier="1",
                        url="https://www.researchgate.net/publication/1_Test_only")
    institutional = deepcopy(repository_record)
    institutional.update(repository="other", name="Test institutional repository",
                         identifier="handle/test", url="https://example.org/handle/test")
    record["repository_records"] = [repository_record, researchgate, institutional]
    write_record(catalog, record)
    page = html(client, f'/research/{record["slug"]}')
    links = page.select(".research-external-links a")
    expected = [item["url"] for item in record["repository_records"]]
    assert [link["href"] for link in links] == expected
    assert page.select_one("#also-available").get_text() == "Also Available On"
    assert "EDITORIAL-NOTE-NOT-FOR-PUBLIC-OUTPUT" not in str(page)
    assert "Synthetic test reviewer" not in str(page)
    canonical = app.config["APP_BASE_URL"].rstrip("/") + "/research/" + record["slug"]
    assert page.select_one('link[rel="canonical"]')["href"] == canonical
    assert page.select_one('meta[name="citation_pdf_url"]')["content"] == canonical + "/paper.pdf"
    graph = json.loads(page.select_one('script[type="application/ld+json"]').string)["@graph"]
    node = next(item for item in graph if item["@type"] == "ScholarlyArticle")
    assert node["sameAs"] == expected
    assert [item["value"] for item in node["identifier"]] == ["0", "1", "handle/test"]
    assert client.get(f'/research/{record["slug"]}/paper.pdf').status_code == 200
    response = client.get(f'/research/{record["slug"]}/submission.json')
    export = response.json
    assert len(export["external_publications"]) == 3
    assert export["zenodo_url"] == expected[0]
    assert export["repository_metadata"]["zenodo"]["related_identifiers"] == [
        {"identifier": canonical, "relation": "isDescribedBy", "scheme": "url"},
    ]
    assert export["repository_metadata"]["researchgate"]["publication_url"] == canonical
    assert response.headers["X-Robots-Tag"] == "noindex, follow"
    for private in ("verification", "indexing", "notes", "checked_by", "EDITORIAL-NOTE"):
        assert private not in json.dumps(export["external_publications"])
    assert "Synthetic test reviewer" not in response.get_data(as_text=True)
    assert export["doi"] is None
    assert "Not peer reviewed" in page.get_text()


@pytest.mark.parametrize("updates", [
    {"repository": "unknown"}, {"repository": []}, {"status": []}, {"status": "indexed"},
    {"status": "published", "verification": None},
    {"status": "pending", "submitted_on": "2026-01-01"},
    {"status": "not_submitted"},
    {"status": "verified_indexed"},
    {"identifier": "999"},
    {"url": "https://sandbox.zenodo.org/records/0"},
    {"url": "https://zenodo.org/deposit/0"},
    {"url": "https://zenodo.org.evil.example/records/0"},
    {"url": "https://zenodo.org/records/0?token=secret"},
    {"url": "https://zenodo.org/records/0#files"},
    {"url": "javascript:alert(1)"},
    {"repository": "researchgate", "url": "https://www.researchgate.net/profile/Test"},
    {"repository": "other", "name": "Zenodo"},
    {"repository": "other", "name": "Test", "url": "https://zenodo.org/records/0"},
    {"repository": "other", "name": "Test", "url": "https://user:secret@example.org/paper"},
    {"repository": "other", "name": "Test", "url": "https://127.0.0.1/paper"},
    {"repository": "other", "name": "Test", "url": "https://[::1]/paper"},
    {"repository": "other", "name": "Test", "url": "https://example.local/paper"},
    {"repository": "other", "name": "Test", "url": "http://example.org/paper"},
    {"repository": "other", "name": "Test", "url": "https://example.org:bad/paper"},
    {"repository": "other", "name": "Test", "url": "https://example.org/%0apaper"},
])
def test_reject_unverified_unsafe_and_mismatched_repository_records(record, repository_record, updates):
    repository_record.update(updates)
    record["repository_records"] = [repository_record]
    with pytest.raises(ResearchValidationError):
        validate_record(record, check_pdf=False)


@pytest.mark.parametrize("field", ["title_matches", "authors_match", "version_matches", "publicly_accessible"])
def test_record_verification_requires_every_identity_check(record, repository_record, field):
    repository_record["verification"][field] = False
    record["repository_records"] = [repository_record]
    with pytest.raises(ResearchValidationError):
        validate_record(record, check_pdf=False)


def test_indexing_requires_separate_dated_evidence(record, repository_record):
    repository_record["status"] = "verified_indexed"
    record["repository_records"] = [repository_record]
    with pytest.raises(ResearchValidationError):
        validate_record(record, check_pdf=False)
    repository_record["indexing"] = {
        "service": "Synthetic indexing service", "checked_by": "Synthetic reviewer",
        "checked_on": "2026-01-03", "evidence_url": "https://example.org/index/test-only-record",
    }
    parsed = validate_record(record, check_pdf=False)
    assert parsed["repository_records"][0]["status_label"] == "Verified Indexed"
    assert "indexing" not in parsed["external_links"][0]
    for updates in (
        {"checked_on": "2025-01-01"},
        {"checked_on": (date.today() + timedelta(days=1)).isoformat()},
        {"evidence_url": repository_record["url"]},
        {"checked_by": ""},
        {"service": ""},
    ):
        candidate = deepcopy(record)
        candidate["repository_records"][0]["indexing"].update(updates)
        with pytest.raises(ResearchValidationError):
            validate_record(candidate, check_pdf=False)


def test_duplicate_records_and_future_verification_rejected(record, repository_record):
    for entries in (
        [repository_record, deepcopy(repository_record)],
        "not a list",
        [None],
    ):
        record["repository_records"] = entries
        with pytest.raises(ResearchValidationError):
            validate_record(record, check_pdf=False)
    record["repository_records"] = [repository_record]
    repository_record["verification"]["checked_on"] = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ResearchValidationError):
        validate_record(record, check_pdf=False)


def test_legacy_zenodo_compatibility_and_explicit_withdrawal(client, catalog, record):
    record.update(doi="10.5281/zenodo.0", doi_registration_confirmed=True,
                  doi_verified_on="2026-01-02",
                  doi_registration_url="https://example.org/test-only-doi-evidence",
                  zenodo_url="https://zenodo.org/records/0")
    write_record(catalog, record)
    page = html(client, f'/research/{record["slug"]}')
    assert len(page.select('.research-external-links a[href="https://zenodo.org/records/0"]')) == 1
    assert page.select_one('meta[name="citation_doi"]')["content"] == record["doi"]
    # Explicit status can withdraw an old link without erasing the registered DOI.
    record["repository_records"] = [{"repository": "zenodo", "status": "not_submitted"}]
    write_record(catalog, record)
    assert not html(client, f'/research/{record["slug"]}').select_one("#also-available")
    assert client.get(f'/research/{record["slug"]}/submission.json').json["zenodo_url"] is None
    record["zenodo_url"] = "https://zenodo.org/records/9"
    with pytest.raises(ResearchValidationError):
        validate_record(record, check_pdf=False)


def test_doi_url_encoding_does_not_change_identifier(client, catalog, record):
    record.update(doi="10.1234/test?only#synthetic", doi_registration_confirmed=True,
                  doi_verified_on="2026-01-02",
                  doi_registration_url="https://example.org/test-only-doi-evidence")
    write_record(catalog, record)
    page = html(client, f'/research/{record["slug"]}')
    url = "https://doi.org/10.1234/test%3Fonly%23synthetic"
    assert page.select_one(f'a[href="{url}"]')
    assert page.select_one('meta[name="citation_doi"]')["content"] == record["doi"]
    assert client.get(f'/research/{record["slug"]}/submission.json').json["doi_url"] == url


def test_submission_report_supports_incomplete_drafts(tmp_path):
    from tools.research_publications import repository_status_report
    raw = {"status": "draft", "repository_records": [
        {"repository": "zenodo", "status": "not_submitted"},
        {"repository": "researchgate", "status": "pending", "submitted_on": "2026-01-01"},
    ]}
    path = tmp_path / "unfinished.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    before = path.read_bytes()
    report = repository_status_report(tmp_path)
    assert [row["status"] for row in report[0]["repositories"]] == ["Not Submitted", "Pending"]
    assert path.read_bytes() == before


def test_existing_orcid_link_is_preserved_not_inferred(client, catalog, record):
    # Only this temporary fixture uses the official ORCID documentation example.
    # It does not assert that the synthetic author owns this ORCID.
    record["authors"][0]["orcid"] = "0000-0002-1825-0097"
    write_record(catalog, record)
    page = html(client, f'/research/{record["slug"]}')
    uri = "https://orcid.org/0000-0002-1825-0097"
    assert uri in page.select_one(f'a[href="{uri}"]').get_text()
    graph = json.loads(page.select_one('script[type="application/ld+json"]').string)["@graph"]
    node = next(item for item in graph if item["@type"] == "ScholarlyArticle")
    assert node["author"][0]["sameAs"] == uri
    assert "sameAs" not in node["author"][1]


def test_repository_requests_never_check_external_services(client, catalog, record, repository_record, monkeypatch):
    import requests
    record["repository_records"] = [repository_record]
    write_record(catalog, record)

    def forbidden(*args, **kwargs):
        raise AssertionError("Research rendering must not call external services")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    for suffix in ("", "/submission.json", "/citation.bib", "/paper.pdf"):
        assert client.get(f'/research/{record["slug"]}{suffix}').status_code == 200
    for path in ("/articles", "/research", "/sitemap.xml"):
        assert client.get(path).status_code == 200


def test_publication_external_links_responsive(app, catalog, record, repository_record):
    from threading import Thread
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server

    repository_record.update(repository="other", name="Synthetic institutional research repository",
                             identifier="test-only-" + "long-identifier-" * 12,
                             url="https://example.org/paper/test-only")
    record["repository_records"] = [repository_record]
    write_record(catalog, record)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/")
                       else route.fulfill(status=200, body="", content_type="application/javascript"))
            for width, height in ((1440, 1000), (768, 1024), (390, 844), (320, 740)):
                page.set_viewport_size({"width": width, "height": height})
                response = page.goto(base + "/research/" + record["slug"], wait_until="networkidle")
                assert response.status == 200
                assert page.locator("#also-available").is_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                assert page.locator(".research-external-links a").get_attribute("href") == repository_record["url"]
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
