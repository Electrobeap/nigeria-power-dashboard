"""Reviewed, file-backed research records; no dashboard or billing dependencies."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from functools import lru_cache
import json
import logging
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
import ipaddress

from flask import current_app, has_app_context

LOGGER = logging.getLogger(__name__)
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "content" / "research"
KINDS = {
    "research-paper": "Research paper",
    "technical-report": "Technical report",
    "working-paper": "Working paper",
    "data-study": "Original data study",
}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){0,2}")
MAX_PDF_BYTES = 5_000_000
MAX_RECORD_BYTES = 1_000_000


class ResearchValidationError(ValueError):
    pass


def content_directory() -> Path:
    configured = current_app.config.get("RESEARCH_CONTENT_DIR") if has_app_context() else None
    return Path(configured or DEFAULT_DIRECTORY).resolve()


def _text(value, field, limit=50000):
    if not isinstance(value, str) or not value.strip():
        raise ResearchValidationError(f"{field} must be non-empty text")
    value = value.strip()
    if len(value) > limit or any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ResearchValidationError(f"{field} contains invalid or excessive text")
    return value


def _date(value, field):
    value = _text(value, field, 10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ResearchValidationError(f"{field} must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ResearchValidationError(f"{field} must use YYYY-MM-DD")
    return value


def _url(value, field):
    value = _text(value, field, 2000)
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or any(char.isspace() for char in value)):
        raise ResearchValidationError(f"{field} must be an absolute HTTPS URL")
    return value


def _texts(value, field):
    if not isinstance(value, list) or not value or len(value) > 500:
        raise ResearchValidationError(f"{field} must be a non-empty list")
    return [_text(item, field) for item in value]


def normalize_orcid(value):
    value = value.removeprefix("https://orcid.org/")
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", value):
        raise ResearchValidationError("Invalid ORCID format")
    digits = value.replace("-", "")
    total = 0
    for digit in digits[:15]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    if digits[-1] != ("X" if check == 10 else str(check)):
        raise ResearchValidationError("Invalid ORCID checksum")
    return f"https://orcid.org/{value}"


REPOSITORY_STATUSES = {
    "not_submitted": "Not Submitted",
    "pending": "Pending",
    "published": "Published",
    "verified_indexed": "Verified Indexed",
}
REPOSITORIES = {"zenodo": "Zenodo", "researchgate": "ResearchGate", "other": None}


def _past_date(value, field):
    value = _date(value, field)
    if value > date.today().isoformat():
        raise ResearchValidationError(f"{field} cannot be in the future")
    return value


def _public_url(value, field):
    """Reject unsafe/private link targets; never request a supplied URL."""
    try:
        value = _url(value, field)
        parsed = urlsplit(value)
        host = parsed.hostname.lower()
        port = parsed.port
    except (ValueError, AttributeError) as exc:
        raise ResearchValidationError(f"{field} must be a public HTTPS URL") from exc
    if (port not in {None, 443} or "\\" in value or
            re.search(r"%0[ad]", value, re.I) or "." not in host or
            host.endswith((".localhost", ".local", ".internal"))):
        raise ResearchValidationError(f"{field} must be a public HTTPS URL")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return value
    raise ResearchValidationError(f"{field} must use a public repository hostname")


def validate_repository_records(raw):
    """Check editorial evidence, not remote registration or indexing."""
    items = raw.get("repository_records", [])
    if not isinstance(items, list) or len(items) > 30:
        raise ResearchValidationError("repository_records must be a list of at most 30 entries")
    records, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ResearchValidationError("Repository entries must be objects")
        entry = deepcopy(item)
        provider = entry.get("repository")
        if not isinstance(provider, str) or provider not in REPOSITORIES:
            raise ResearchValidationError("repository must be zenodo, researchgate, or other")
        entry["name"] = REPOSITORIES[provider] or _text(entry.get("name"), "repository name", 150)
        if provider == "other" and entry["name"].casefold() in {"zenodo", "researchgate"}:
            raise ResearchValidationError("Use the named repository type")
        status = entry.get("status")
        if not isinstance(status, str) or status not in REPOSITORY_STATUSES:
            raise ResearchValidationError("Invalid repository submission status")
        entry["status_label"] = REPOSITORY_STATUSES[status]
        if entry.get("notes"):
            entry["notes"] = _text(entry["notes"], "editorial notes", 2000)
        if status in {"not_submitted", "pending"}:
            if any(entry.get(field) for field in ("url", "identifier", "verification", "indexing")):
                raise ResearchValidationError("Unpublished submissions cannot claim external records")
            if status == "pending":
                entry["submitted_on"] = _past_date(entry.get("submitted_on"), "submission date")
            elif entry.get("submitted_on"):
                raise ResearchValidationError("Not Submitted cannot have a submission date")
        else:
            entry["url"] = _public_url(entry.get("url"), "repository URL")
            entry["identifier"] = _text(entry.get("identifier"), "repository identifier", 255)
            parsed = urlsplit(entry["url"])
            if parsed.query or parsed.fragment:
                raise ResearchValidationError("Use a stable repository URL without query or fragment")
            if provider == "zenodo":
                match = re.fullmatch(r"https://zenodo\.org/records/([0-9]+)", entry["url"])
                if not match or entry["identifier"] != match[1]:
                    raise ResearchValidationError("Zenodo identifier must match its published record URL")
            elif provider == "researchgate":
                match = re.fullmatch(
                    r"https://(?:www\.)?researchgate\.net/publication/([0-9]+)(?:_[A-Za-z0-9_~.%()-]+)?",
                    entry["url"],
                )
                if not match or entry["identifier"] != match[1]:
                    raise ResearchValidationError("ResearchGate identifier must match a publication URL")
            elif parsed.hostname.lower() in {"zenodo.org", "www.zenodo.org", "researchgate.net", "www.researchgate.net"}:
                raise ResearchValidationError("Use the named repository type")
            proof = entry.get("verification")
            if not isinstance(proof, dict):
                raise ResearchValidationError("Published repository records require verification")
            for field in ("title_matches", "authors_match", "version_matches", "publicly_accessible"):
                if proof.get(field) is not True:
                    raise ResearchValidationError(f"Repository verification requires {field}=true")
            proof["checked_on"] = _past_date(proof.get("checked_on"), "record verification date")
            proof["checked_by"] = _text(proof.get("checked_by"), "record reviewer", 150)
            proof["evidence_url"] = _public_url(proof.get("evidence_url"), "record evidence URL")
            if entry.get("submitted_on"):
                entry["submitted_on"] = _past_date(entry["submitted_on"], "submission date")
                if proof["checked_on"] < entry["submitted_on"]:
                    raise ResearchValidationError("Verification cannot precede submission")
            if status == "verified_indexed":
                indexing = entry.get("indexing")
                if not isinstance(indexing, dict):
                    raise ResearchValidationError("Verified Indexed requires separate indexing evidence")
                indexing["service"] = _text(indexing.get("service"), "indexing service", 150)
                indexing["evidence_url"] = _public_url(indexing.get("evidence_url"), "indexing evidence URL")
                indexing["checked_by"] = _text(indexing.get("checked_by"), "indexing reviewer", 150)
                indexing["checked_on"] = _past_date(indexing.get("checked_on"), "index verification date")
                if indexing["checked_on"] < proof["checked_on"]:
                    raise ResearchValidationError("Index verification cannot precede record verification")
                if indexing["evidence_url"] == entry["url"]:
                    raise ResearchValidationError("A repository landing page alone is not indexing evidence")
            elif entry.get("indexing"):
                raise ResearchValidationError("Only Verified Indexed may claim indexing evidence")
        # One entry per repository keeps status tracking unambiguous.
        identity = (provider, entry["name"].casefold())
        if identity in seen:
            raise ResearchValidationError("Duplicate repository submission")
        seen.add(identity)
        records.append(entry)
    return records


def public_repository_links(record):
    """Allowlist public bibliographic fields; editorial notes/evidence stay out."""
    links = [
        {key: item[key] for key in ("repository", "name", "identifier", "url")}
        for item in record.get("repository_records", [])
        if item["status"] in {"published", "verified_indexed"}
    ]
    # Backward compatibility: the legacy Zenodo field already required DOI approval.
    # An explicit workflow entry takes precedence, including withdrawn/pending links.
    if record.get("zenodo_url") and not any(
            item["repository"] == "zenodo" for item in record.get("repository_records", [])):
        links.append({"repository": "zenodo", "name": "Zenodo",
                      "identifier": record["zenodo_url"].rsplit("/", 1)[-1],
                      "url": record["zenodo_url"]})
    return links


def pdf_path(record, directory=None):
    filename = record.get("pdf_file")
    if not filename:
        return None
    if not isinstance(filename, str) or not re.fullmatch(r"papers/[a-z0-9][a-z0-9.-]*\.pdf", filename):
        raise ResearchValidationError("pdf_file must name a PDF under papers/")
    root = Path(directory or content_directory()).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root / "papers"):
        raise ResearchValidationError("PDF path escapes the papers directory")
    return path


def validate_record(raw, directory=None, *, check_pdf=True):
    """Validate editorial inputs; never infer authors, credentials, or results."""
    if not isinstance(raw, dict):
        raise ResearchValidationError("Research record must be an object")
    record = deepcopy(raw)
    record.pop("doi_url", None)
    for field in ("slug", "title", "abstract", "version", "license"):
        record[field] = _text(record.get(field), field)
    if not SLUG.fullmatch(record["slug"]) or len(record["slug"]) > 160:
        raise ResearchValidationError("Invalid publication slug")
    if not VERSION.fullmatch(record["version"]):
        raise ResearchValidationError("version must be numeric, e.g. 1.0")
    if record.get("publication_type") not in KINDS:
        raise ResearchValidationError("Unknown publication_type")
    if record.get("status") not in {"draft", "published"}:
        raise ResearchValidationError("status must be draft or published")
    for field in ("published_at", "updated_at"):
        record[field] = _date(record.get(field), field)
    if record["updated_at"] < record["published_at"]:
        raise ResearchValidationError("updated_at precedes published_at")
    if record["status"] == "published":
        if record.get("publication_approved") is not True or record.get("rights_confirmed") is not True:
            raise ResearchValidationError("Publication requires editorial and rights approval")
    authors = record.get("authors")
    if not isinstance(authors, list) or not authors or len(authors) > 100:
        raise ResearchValidationError("At least one named author is required")
    names = set()
    for author in authors:
        if not isinstance(author, dict):
            raise ResearchValidationError("Each author must be an object")
        author["given_name"] = _text(author.get("given_name"), "author given_name", 150)
        author["family_name"] = _text(author.get("family_name"), "author family_name", 150)
        author["name"] = f'{author["given_name"]} {author["family_name"]}'
        if author["name"].casefold() in names:
            raise ResearchValidationError("Duplicate author")
        names.add(author["name"].casefold())
        if author["name"].casefold() in {"nigeria power data", "nigeria power data team"}:
            raise ResearchValidationError("Research authors must be actual named individuals")
        affiliations = author.get("affiliations", [])
        if not isinstance(affiliations, list):
            raise ResearchValidationError("Author affiliations must be a list")
        author["affiliations"] = [_text(item, "affiliation", 300) for item in affiliations]
        if author.get("orcid"):
            author["orcid"] = normalize_orcid(_text(author["orcid"], "ORCID", 80))
    for field in ("keywords", "methodology", "findings", "limitations", "assumptions"):
        record[field] = _texts(record.get(field), field)
    references = record.get("references")
    if not isinstance(references, list) or not references:
        raise ResearchValidationError("References are required")
    for reference in references:
        if not isinstance(reference, dict):
            raise ResearchValidationError("References must be objects")
        reference["citation"] = _text(reference.get("citation"), "reference citation")
        if reference.get("url"):
            reference["url"] = _url(reference["url"], "reference URL")
    sources = record.get("data_provenance")
    if not isinstance(sources, list) or not sources:
        raise ResearchValidationError("Data provenance is required")
    for source in sources:
        if not isinstance(source, dict):
            raise ResearchValidationError("Data provenance entries must be objects")
        for field in ("citation", "coverage", "processing", "license"):
            source[field] = _text(source.get(field), f"source {field}")
        source["url"] = _url(source.get("url"), "source URL")
        source["accessed_on"] = _date(source.get("accessed_on"), "source accessed_on")
        if source.get("data_kind") not in {"measured", "estimated", "documentary"}:
            raise ResearchValidationError("Sources must distinguish measured, estimated, or documentary data")
    record.setdefault("peer_review_status", "not_peer_reviewed")
    if record["peer_review_status"] not in {"not_peer_reviewed", "externally_peer_reviewed"}:
        raise ResearchValidationError("Invalid peer_review_status")
    if record["peer_review_status"] == "externally_peer_reviewed":
        record["peer_review_url"] = _url(record.get("peer_review_url"), "peer review evidence")
    if record.get("doi"):
        record["doi"] = _text(record["doi"], "DOI", 255)
        if not re.fullmatch(r"10\.\d{4,9}/[^\s<>\"{}]+", record["doi"]):
            raise ResearchValidationError("DOI must be a registered identifier, not a URL")
        record["doi_verified_on"] = _past_date(record.get("doi_verified_on"), "DOI verification date")
        record["doi_registration_url"] = _public_url(record.get("doi_registration_url"), "DOI registration evidence")
        if record.get("doi_registration_confirmed") is not True:
            raise ResearchValidationError("DOI registration must be manually confirmed")
        record["doi_url"] = "https://doi.org/" + quote(record["doi"], safe="/")
    if record.get("zenodo_url"):
        record["zenodo_url"] = _url(record["zenodo_url"], "Zenodo URL")
        if not re.fullmatch(r"https://zenodo\.org/records/\d+", record["zenodo_url"]):
            raise ResearchValidationError("Use a published Zenodo record URL")
        if (record.get("doi") or "").lower() != "10.5281/zenodo." + record["zenodo_url"].rsplit("/", 1)[-1]:
            raise ResearchValidationError("Legacy Zenodo URL must match its exact registered DOI")
    record["repository_records"] = validate_repository_records(record)
    for entry in record["repository_records"]:
        if (record.get("zenodo_url") and entry["repository"] == "zenodo"
                and entry.get("url") and entry["url"] != record["zenodo_url"]):
            raise ResearchValidationError("Legacy and current Zenodo records disagree")
    record["external_links"] = public_repository_links(record)
    if record.get("license_url"):
        record["license_url"] = _url(record["license_url"], "license URL")
    path = pdf_path(record, directory)
    if path and check_pdf:
        if record.get("pdf_publication_approved") is not True:
            raise ResearchValidationError("PDF requires approval of text, attribution, and distribution rights")
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_PDF_BYTES:
            raise ResearchValidationError("PDF must exist and be no larger than 5 MB")
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ResearchValidationError("Invalid PDF header")
    record["url"] = f'/research/{record["slug"]}'
    record["type_label"] = KINDS[record["publication_type"]]
    record["description"] = " ".join(record["abstract"].split())[:180]
    return record


def read_records(directory=None, *, strict=False):
    root = Path(directory or content_directory()).resolve()
    records, seen = [], set()
    for path in sorted(root.glob("*.json")):
        try:
            if path.stat().st_size > MAX_RECORD_BYTES:
                raise ResearchValidationError("Research record exceeds 1 MB")
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Unfinished drafts are allowed on disk but never served publicly.
            if not strict and isinstance(raw, dict) and raw.get("status") == "draft":
                continue
            record = validate_record(raw, root)
            if path.stem != record["slug"] or record["slug"] in seen:
                raise ResearchValidationError("Filename must match a unique publication slug")
            seen.add(record["slug"])
            records.append(record)
        except (OSError, ValueError, TypeError) as exc:
            if strict:
                raise ResearchValidationError(f"{path.name}: {exc}") from exc
            LOGGER.error("research_record_rejected file=%s reason=%s", path.name, exc)
    return records


@lru_cache(maxsize=1)
def _cached_records(directory, fingerprint):
    return read_records(directory)


def list_publications():
    root = content_directory()
    # Include PDFs so a missing or replaced paper cannot leave stale citation links.
    paths = sorted(root.glob("*.json")) + sorted((root / "papers").glob("*.pdf"))
    fingerprint = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
    today = date.today().isoformat()
    records = _cached_records(str(root), fingerprint)
    return deepcopy(sorted(
        (item for item in records if item["status"] == "published"
         and item["published_at"] <= today and item["updated_at"] <= today),
        key=lambda item: (item["published_at"], item["slug"]), reverse=True,
    ))


def get_publication(slug):
    return next((item for item in list_publications() if item["slug"] == slug), None)


def recommended_citation(record, base_url):
    names = "; ".join(f'{author["family_name"]}, {author["given_name"]}' for author in record["authors"])
    link = record["doi_url"] if record.get("doi") else base_url.rstrip("/") + record["url"]
    return (f'{names} ({record["published_at"][:4]}). {record["title"]} '
            f'(Version {record["version"]}) [{record["type_label"]}]. Nigeria Power Data. {link}')


def _bibtex_text(value):
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
                    "%": r"\%", "&": r"\&", "#": r"\#", "_": r"\_",
                    "$": r"\$", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in " ".join(value.split()))


def bibtex(record, base_url):
    fields = {
        "title": record["title"],
        "author": " and ".join(f'{a["family_name"]}, {a["given_name"]}' for a in record["authors"]),
        "year": record["published_at"][:4],
        "date": record["published_at"],
        "institution": "Nigeria Power Data",
        "type": record["type_label"],
        "version": record["version"],
        "url": base_url.rstrip("/") + record["url"],
        "note": f'Version {record["version"]}; ' + (
            "External peer review evidence available" if record["peer_review_status"] == "externally_peer_reviewed"
            else "Not peer reviewed"),
    }
    if record.get("doi"):
        fields["doi"] = record["doi"]
    lines = [f'@techreport{{npd-{record["slug"]},']
    lines.extend(f"  {key} = {{{_bibtex_text(value)}}}," for key, value in fields.items())
    return "\n".join(lines + ["}", ""])


def scholarly_graph(record, graph, base_url):
    graph = deepcopy(graph)
    url = base_url.rstrip("/") + record["url"]
    node = {
        "@type": "ScholarlyArticle", "@id": url + "#publication",
        "url": url, "headline": record["title"], "name": record["title"],
        "description": record["description"], "abstract": record["abstract"],
        "datePublished": record["published_at"], "dateModified": record["updated_at"],
        "version": record["version"], "genre": record["type_label"],
        "keywords": record["keywords"], "inLanguage": "en", "isAccessibleForFree": True,
        "mainEntityOfPage": {"@id": url + "#webpage"},
        "publisher": {"@id": base_url.rstrip("/") + "/#organization"},
        "author": [],
        "citation": [
            {"@type": "CreativeWork", "name": item["citation"],
             **({"url": item["url"]} if item.get("url") else {})}
            for item in record["references"]
        ],
    }
    for author in record["authors"]:
        person = {"@type": "Person", "name": author["name"],
                  "givenName": author["given_name"], "familyName": author["family_name"]}
        if author["affiliations"]:
            person["affiliation"] = [{"@type": "Organization", "name": name} for name in author["affiliations"]]
        if author.get("orcid"):
            person["@id"] = author["orcid"]
            person["sameAs"] = author["orcid"]
        node["author"].append(person)
    if record.get("pdf_file"):
        node["encoding"] = {"@type": "MediaObject", "encodingFormat": "application/pdf",
                            "contentUrl": url + "/paper.pdf"}
    if record.get("doi"):
        node["identifier"] = {"@type": "PropertyValue", "propertyID": "DOI", "value": record["doi"]}
        node["sameAs"] = [record["doi_url"]]
    external = record.get("external_links", [])
    if external:
        node["sameAs"] = list(dict.fromkeys(node.get("sameAs", []) + [item["url"] for item in external]))
        identifiers = [node["identifier"]] if "identifier" in node else []
        identifiers.extend({"@type": "PropertyValue", "propertyID": item["name"],
                            "value": item["identifier"], "url": item["url"]} for item in external)
        node["identifier"] = identifiers
    if record.get("license_url"):
        node["license"] = record["license_url"]
    for existing in graph["@graph"]:
        if existing.get("@id") == url + "#webpage":
            existing["mainEntity"] = {"@id": node["@id"]}
    graph["@graph"].append(node)
    return graph
