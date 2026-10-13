# Verified external research records

This is an editorial configuration workflow, not an automated submission or
indexing service. It applies only to genuine research records under
`grid_monitor/content/research/`. Educational `/articles` keep their existing
URLs and Article metadata; they never receive scholarly repository claims.

No real external records, authors, DOIs, or indexing results are supplied by
this change. Source reuse rights remain unconfirmed. Existing study protocols
must stay unpublished until data, rights, authorship, and editorial approval are
complete. Repository publication does not establish peer review.

## Configuration

Add `repository_records` to a research JSON record. An omitted array means no
new repository submissions. The blank research template includes Zenodo and
ResearchGate with `not_submitted` status and no fabricated identifiers.

| Stored status | Editorial label | Required evidence | Public effect |
| --- | --- | --- | --- |
| not_submitted | Not Submitted | None; no submission date or record claims | No link |
| pending | Pending | Actual submitted_on date | No link |
| published | Published | Identifier, stable public URL, full record verification | Also Available On link |
| verified_indexed | Verified Indexed | All Published fields plus independent indexing evidence | Same public link; no automatic indexing badge |

Each repository has one status entry per publication version. Use
`repository: zenodo`, `researchgate`, or `other`. For other repositories,
supply their actual display `name` (for example an institutional repository).
There is no provider SDK, database migration, write API, or new runtime dependency.

### Published record fields

- `repository`: repository type.
- `name`: required only for other repositories; built-in names are canonical.
- `status`: published or verified_indexed.
- `identifier`: the actual repository record ID. Zenodo and ResearchGate
  numeric IDs must match the supplied URL. Do not derive one from a title.
- `url`: stable public HTTPS publication landing page, not a profile, search
  page, private draft, upload endpoint, sandbox record, signed link, or token URL.
  Query strings and fragments are rejected for record links.
- `submitted_on`: optional actual submission date, YYYY-MM-DD.
- `verification.checked_on`: actual review date, not in the future.
- `verification.checked_by`: actual editorial reviewer or accountable team.
- `verification.evidence_url`: public evidence checked by the reviewer.
- `verification.title_matches`, `authors_match`, `version_matches`,
  `publicly_accessible`: each must be the boolean true following a real check.
- `notes`: optional short editorial explanation. Never put access tokens,
  personal contact details, confidential review notes, or other secrets here.

For `verified_indexed`, add `indexing.service`, `indexing.evidence_url`,
`indexing.checked_on`, and `indexing.checked_by`. Evidence must refer to an
actual matching result in the named indexing service. A DOI resolution, a
successful deposit, a Scholar-compatible meta tag, a submission confirmation,
or the repository landing page alone does not prove indexing. Recheck indexing
after verifying record identity; store the observation date, not a guarantee of
continued inclusion.

Configuration validation checks syntax, consistency, required attestations and
dates. It cannot establish factual identity or remote existence. Editors must
open the links, resolve any redirects, inspect the title, complete author list,
version and rights, and review evidence before approving the PR. The application
does not scrape ResearchGate or Scholar and does not make external calls while
rendering pages. No remote outage can stall the research library.

## Editorial process

1. Start with Not Submitted. Never guess an author, affiliation, ORCID or DOI.
2. After author/rights approval and an actual submission, set Pending and its
   real submitted_on date. Keep private deposit URLs and credentials outside Git.
3. Once the record is published, verify it manually and fill the Published
   fields above. For Zenodo use https://zenodo.org/records/ACTUAL_ID. For
   ResearchGate use the real /publication/ID or /publication/ID_Title URL.
4. Compare the manuscript version and every author, not merely a similar title.
   Link only the same publication version. Related studies belong in references,
   not sameAs or Also Available On.
5. Resolve any registered DOI at https://doi.org/ and record the existing DOI
   approval fields. Reserved draft DOIs must not be used. Prefer the exact
   version DOI. A paper deposited with its existing publisher DOI need not have
   a Zenodo-issued DOI to use the new repository_records workflow.
6. Do not change manuscript publication dates merely because a repository status
   changed. Git records the editorial change; checked_on records verification.
7. Run validation and review the PR. Only eligible published research pages
   expose links; drafts remain inaccessible even if their repository status
   says Published.
8. Set Verified Indexed only after directly observing and recording a genuine
   matching indexing result. Search visibility and inclusion are not guaranteed.

To remove a stale public link, remove its entry, or clear its record/evidence
fields and use Pending for an actual replacement submission, or Not Submitted
for no current submission. Record the reason in nonconfidential notes. Do not
reuse a status while leaving contradictory claims attached.

The older zenodo_url field remains supported with its existing registered DOI
approval, now requiring an exact matching version-record ID. Migrate old fields
to repository_records during editorial review. A new explicit Zenodo status
takes precedence over the legacy link, so Pending/Not Submitted can suppress it.
Do not specify conflicting old and new Zenodo URLs. Registered DOI citation
metadata is independent of the repository submission status.

## Visibility and citation integrity

- Also Available On is absent unless approved external links exist.
- JSON-LD adds only those same-publication links to ScholarlyArticle.sameAs and
  their identifiers to PropertyValue entries. It makes no indexing assertion.
- Registered DOIs resolve via the official doi.org HTTPS landing URL; URL-reserved
  characters are encoded without changing the DOI in citation metadata/BibTeX.
- Author-supplied ORCIDs keep checksum validation and HTTPS URI links. Valid syntax
  does not prove profile ownership; authors must confirm association.
- Highwire tags, local canonical URLs, public PDFs, sources and citation downloads
  retain their existing behavior. External pages never replace the NPD canonical.
- Editorial reviewer names, evidence, notes and pending submissions are not
  serialized into HTML/JSON-LD or submission exports. **Git is public:** this is
  output minimization, not confidential storage.

## Manual submission metadata

Download `/research/<slug>/submission.json` for an eligible paper. The existing
fields remain available. It additionally includes verified external records and:

- `repository_metadata.zenodo.related_identifiers`: the canonical NPD HTML URL
  with `scheme: url` and `relation: isDescribedBy`, using Zenodo's documented
  deposition vocabulary. This links the deposited work to its NPD description.
- `repository_metadata.researchgate.publication_url`: the canonical source URL
  for the author to paste into an applicable source/description field when the
  current submission form supports it.

This is a metadata fragment for manual review, not an upload-ready API payload.
Complete the repository's required fields and rights checks yourself. The system
does not submit, deposit, upload files, reserve/register DOIs, or create ResearchGate
listings. It supplies no API token and does not use anyone's account automatically.

## Offline review and CI

From Windows PowerShell at the repository root:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-research.txt
python -m playwright install chromium
python -m compileall -q app.py grid_monitor tools tests
python -m tools.research_publications repositories
python -m tools.research_publications validate
python -m pytest -q tests/test_research.py
python -m pytest -q
~~~

The repositories command is a read-only status overview. Use
`--directory .\path\to\editorial-records` to review incomplete drafts outside
the publication catalog. It validates repository workflow fields but not the
whole manuscript. The validate command remains the full strict catalog/PDF gate.

GitHub Actions runs syntax checks, both editorial commands, and the entire test
suite including controlled Chromium desktop/tablet/mobile checks. Synthetic test
IDs never enter the deployed catalog and are not real verification results.
No merge or deployment is triggered by this workflow.

## Primary references

- [Zenodo deposition metadata and related identifiers](https://developers.zenodo.org/)
- [ResearchGate author-managed research submission](https://help.researchgate.net/research-and-publications/how-to-add-research)
- [ORCID identifier structure](https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier)
- [ORCID publication display guidance](https://info.orcid.org/guidelines-on-the-display-of-orcid-ids-in-publications/)
- [Google Scholar inclusion guidelines](https://scholar.google.com/intl/en/scholar/inclusion.html)
