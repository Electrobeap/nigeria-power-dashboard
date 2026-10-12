# Scholarly publishing

## Scope and access

Research is separate from educational Articles. The /research library lists only
reviewed, published research records: research papers, technical reports, working
papers, and original data studies. No existing post is relabeled and no research,
author, affiliation, DOI, or credential is seeded.

Abstracts, full HTML records, eligible PDFs, and citations are public. No sign-in,
paywall, ad placeholder, consent interstitial, or analytics API is required to
read them. Future analytics/data subscription entitlements must explicitly leave
/research and its paper routes public. This branch does not modify billing.

Google Scholar discovery is eligibility, not a promise of indexing or peer review.
Original research must be written and approved by its real authors. ResearchGate
submission is manual; this system never logs into, uploads to, or claims listing
on ResearchGate.

## Architecture

- grid_monitor/services/research.py validates and reads JSON research records.
- grid_monitor/content/research/ contains reviewed records and papers/.
- grid_monitor/routes/research.py serves HTML, PDFs, BibTeX, and submission records.
- Research templates reuse the existing social and structured-data helpers,
  organization, website, breadcrumbs, navigation, analytics, and CSS theme.
- The shared public URL registry adds published records to sitemap and existing
  IndexNow notifications. No crawler or scheduler changes are required.
- One small catalog cache is invalidated when record/PDF size or modification
  time changes. Date eligibility is rechecked on every request. No historical
  SQL, scraping, network calls, or PDF generation runs in page requests.
- Invalid records are logged and excluded rather than breaking other pages.
  Offline validation reports them as failures.

This follows the existing file-backed publishing architecture. There is no new
database schema or migration. JSON records are portable to a future editorial
store without changing the public routes.

Optional RESEARCH_CONTENT_DIR selects a local directory of reviewed records.
The default is grid_monitor/content/research. On Render free tier, commit records
and PDFs to Git for persistence; do not upload them into an ephemeral filesystem.
Keep this directory outside static/ to prevent bypassing publication checks.

## Routes

| Route | Purpose |
| --- | --- |
| /research | Crawlable library and GET search/type filter |
| /research/<slug> | Canonical publication, abstract, content, metadata |
| /research/<slug>/paper.pdf | Public, searchable, approved PDF when supplied |
| /research/<slug>/citation.bib | BibTeX download |
| /research/<slug>/submission.json | Public metadata for manual author submission |

Search/filter results are noindex,follow; the unfiltered library and all eligible
publications remain indexable. Citation/submission exports are noindex,follow.
robots.txt already permits these routes. Drafts, future-dated records, unapproved
records, and unavailable papers do not appear in the library or sitemap.
An abstract-only record may omit pdf_file; no PDF metadata/link is then emitted.

## Editorial workflow

1. Copy docs/research-record.template.json outside the live catalog while writing.
   Fill real given/family names in author order, actual affiliations (an empty
   list is valid for unaffiliated authors), and author-confirmed ORCIDs if known.
   ORCID format/checksum validation does not verify personal identity.
2. Supply the complete author-written abstract, keywords, methods, findings,
   limitations, explicit assumptions, and formal references. Plain text is
   escaped by the templates; HTML is not accepted as executable content.
3. Describe each source: citation, HTTPS URL, date accessed, coverage, processing,
   rights, and measured/estimated/documentary classification. Measured means
   reported observations from that source, not independent NPD verification.
   Planning estimates, inferred allocations, simulated loading, and forecasts
   must be labeled estimated. Explain uncertainty, missing data, transformations,
   model assumptions, and reproducibility in the manuscript.
4. Select a numeric version (such as 1.0). Use an immutable version-specific slug
   such as <real-title>-v1 and matching filename <slug>.json. Do not rewrite a
   published version's author list, data, results, or PDF silently. Publish a new
   version with a new slug and retain the old record, citation, and PDF.
5. Use not_peer_reviewed by default. An externally_peer_reviewed claim requires
   a public HTTPS evidence URL and editorial verification; it is never inferred
   from a DOI, Zenodo deposit, publication type, or author affiliation.
6. Name the PDF papers/<slug>-v1.pdf. Generate it from the completed record using
   the offline tool below, or supply an author-prepared searchable PDF. Check
   actual title, author order, affiliations, abstract, body, references, version,
   licensing, page breaks, special characters, and accessibility visually.
7. Confirm the authors' permission, source rights, and publication license.
   Only then set publication_approved, rights_confirmed, and (if used)
   pdf_publication_approved to true, status to published, and actual publication
   and update dates in YYYY-MM-DD. Filenames must match the record slug.
8. Run all validation, review the change in a PR, then publish through the normal
   approved deployment process. Changes to the public URL registry flow through
   existing IndexNow notifications.

The blank template is intentionally invalid until real author content is supplied.
Do not put an unfinished template in the deployment catalog. Complete drafts are
accepted by strict validation and remain hidden on the website. A public Git
repository still exposes committed draft files; keep confidential manuscripts
outside Git until publication is approved.

## PDFs

Install editorial/test tools separately; production requirements are unchanged:

~~~powershell
python -m pip install -r requirements-research.txt
python -m tools.research_publications build .\path\to\complete-record.json
python -m tools.research_publications validate
~~~

The build command writes to the record's relative papers/ path. It does not
publish, approve, deposit, register, or upload anything. Existing files are not
overwritten unless --overwrite is explicitly supplied. For non-Latin glyphs,
supply appropriate licensed Unicode fonts using --font and --bold-font.
Default embedded Vera fonts support common Latin author names; missing glyphs
cause a validation error, not silent substitutions.

PDFs must be unencrypted, under 5 MB, and contain searchable text, with a prominent
title, all authors on the first page, an abstract, academic sections, numbered
references, version/date, and page numbers. The offline validator extracts text
to check attribution and HTML/PDF consistency. It is not a PDF/UA accessibility
certifier or a scientific peer reviewer. Visually inspect the final author paper
and ensure meaningful text order, accessible tables, and figure descriptions.

No real papers were supplied for this implementation, so no production PDFs are
generated. PDF rendering is exercised only with explicitly synthetic test data.

## DOIs and repositories

- Deposit real work on Zenodo manually after author/rights approval.
- A reserved draft DOI is not proof of a published record. Publish the deposit,
  resolve its DOI, and check that the title, authors, date, and version agree.
- Copy the actual registered identifier into doi without the https://doi.org/
  prefix. Set doi_registration_confirmed=true, doi_verified_on, and the public
  doi_registration_url used for the editorial check.
- For Zenodo, also set zenodo_url to its published https://zenodo.org/records/ID.
  Prefer the version-specific DOI for an exact-version citation. Do not substitute
  a concept DOI without understanding its version semantics.
- The application validates syntax and approval fields, not remote registration.
  It never generates identifiers or performs external DOI checks during requests.
- Bibliographic exports omit DOI completely when one has not been registered.
- Authors can download submission.json, review it, and manually use the content
  in ResearchGate. They must check manuscript sharing rights themselves.

## Validation and release

~~~powershell
git fetch origin
git switch feature/research-publishing-discovery
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-research.txt
python -m compileall -q app.py grid_monitor tools tests
python -m tools.research_publications validate
python -m pytest -q tests/test_research.py
python -m pytest -q
~~~

The research-validation GitHub Actions workflow runs syntax, catalog/PDF checks,
and the complete test suite on the feature branch and matching pull requests.
It has read-only repository permissions and does not deploy.

Before approval, inspect a real publication and PDF on desktop/mobile, validate
the JSON-LD in Schema.org Validator, and inspect the source for exactly one
canonical, one social tag set, one ScholarlyArticle, and accurate Highwire tags.
A rich-results tool does not certify Google Scholar inclusion. After an approved
release, verify the sitemap and crawlable PDF and subsequently search Scholar
for the exact publication title. Indexing is controlled by the indexing service.

## Primary specifications

- Google Scholar inclusion: https://scholar.google.com/intl/en/scholar/inclusion.html
- ScholarlyArticle: https://schema.org/ScholarlyArticle
- Zenodo DOI guidance: https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/
- ORCID format/checksum: https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier
