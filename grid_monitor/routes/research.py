"""Public scholarly library. All requests are local reads with no external calls."""
from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, send_file

from grid_monitor.services.articles import search_articles
from grid_monitor.services.research import (
    KINDS, bibtex, get_publication, list_publications, pdf_path,
    recommended_citation, scholarly_graph,
)
from grid_monitor.services.social_meta import build_social_meta
from grid_monitor.services.structured_data import build_structured_data

research_bp = Blueprint("research", __name__, url_prefix="/research")


def _publication(slug):
    record = get_publication(slug)
    if record is None:
        abort(404)
    return record


def _context(title, description, path, record=None):
    base = current_app.config["APP_BASE_URL"].rstrip("/")
    breadcrumbs = [{"name": "Home", "path": "/"}, {"name": "Research", "path": "/research"}]
    if record:
        breadcrumbs.append({"name": title, "path": path})
    graph = build_structured_data(
        title=title, description=description, path=path, breadcrumbs=breadcrumbs,
        include_datasets=False, page_type="WebPage" if record else "CollectionPage",
    )
    if record:
        graph = scholarly_graph(record, graph, base)
    return {
        "title": title, "description": description, "canonical_url": base + path,
        "breadcrumbs": breadcrumbs, "structured_data": graph,
        "social_meta": build_social_meta(
            title=title, description=description, path=path,
            og_type="article" if record else "website",
            published_time=record["published_at"] if record else None,
            modified_time=record["updated_at"] if record else None,
        ),
    }


@research_bp.get("")
def library():
    query = request.args.get("q", "").strip()[:200]
    kind = request.args.get("type", "")
    if kind and kind not in KINDS:
        abort(404)
    records = list_publications()
    has_publications = bool(records)
    if kind:
        records = [item for item in records if item["publication_type"] == kind]
    if query:
        terms = query.casefold().split()
        records = [item for item in records if all(
            term in " ".join([item["title"], item["abstract"], *item["keywords"],
                              *(author["name"] for author in item["authors"])]).casefold()
            for term in terms
        )]
    guides = search_articles(query=query, per_page=12)["articles"]
    if query:
        # Retain full-text matches, bringing explicit topic matches to the top.
        terms = query.casefold().split()
        guides.sort(key=lambda guide: sum(
            5 * (term in guide["title"].casefold())
            + 3 * (term in guide["category"].casefold())
            + 2 * (term in " ".join(guide["keywords"]).casefold())
            + (term in guide["description"].casefold())
            for term in terms
        ), reverse=True)
    return render_template(
        "research/library.html", records=records, query=query, kind=kind, kinds=KINDS,
        has_publications=has_publications,
        guides=guides,
        noindex=bool(request.query_string),
        **_context("Research Library", "Original electricity research, technical reports, working papers, and data studies from Nigeria Power Data.", "/research"),
    )


@research_bp.get("/<slug>")
def publication(slug):
    record = _publication(slug)
    return render_template(
        "research/publication.html", publication=record,
        citation=recommended_citation(record, current_app.config["APP_BASE_URL"]),
        bibtex_text=bibtex(record, current_app.config["APP_BASE_URL"]), noindex=False,
        **_context(record["title"], record["description"], record["url"], record),
    )


@research_bp.get("/<slug>/paper.pdf")
def paper(slug):
    record = _publication(slug)
    path = pdf_path(record)
    if path is None or not path.is_file():
        abort(404)
    response = send_file(path, mimetype="application/pdf", conditional=True,
                         download_name=f'{slug}-v{record["version"]}.pdf')
    response.headers["X-Robots-Tag"] = "index, follow"
    response.headers["Link"] = f'<{current_app.config["APP_BASE_URL"].rstrip("/")}{record["url"]}>; rel="canonical"'
    return response


@research_bp.get("/<slug>/citation.bib")
def citation_export(slug):
    record = _publication(slug)
    response = Response(bibtex(record, current_app.config["APP_BASE_URL"]), mimetype="application/x-bibtex")
    response.headers["Content-Disposition"] = f'attachment; filename="{slug}.bib"'
    response.headers["X-Robots-Tag"] = "noindex, follow"
    return response


@research_bp.get("/<slug>/submission.json")
def submission_export(slug):
    record = _publication(slug)
    base = current_app.config["APP_BASE_URL"].rstrip("/")
    response = jsonify({
        "submission_method": "manual",
        "instructions": "The author must review rights and submit through their own ResearchGate account. This export does not upload or list the work.",
        "title": record["title"], "authors": record["authors"], "abstract": record["abstract"],
        "keywords": record["keywords"], "publication_date": record["published_at"],
        "publication_type": record["type_label"], "version": record["version"],
        "review_status": record["peer_review_status"], "license": record["license"],
        "doi": record.get("doi"), "zenodo_url": record.get("zenodo_url"),
        "url": base + record["url"],
        "pdf_url": base + record["url"] + "/paper.pdf" if record.get("pdf_file") else None,
        "recommended_citation": recommended_citation(record, base),
    })
    response.headers["Content-Disposition"] = f'attachment; filename="{slug}-submission.json"'
    response.headers["X-Robots-Tag"] = "noindex, follow"
    return response
