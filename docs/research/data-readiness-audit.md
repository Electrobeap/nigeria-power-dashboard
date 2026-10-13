# Research data readiness

Status: pre-analysis audit. No research publication is approved.
The owner confirmed that reuse rights for stored NISO/NIGGRID readings have not
yet been established. Research calculations and empirical manuscript findings
remain blocked pending documented rights and an author-approved dataset.

## What is verified from repository evidence

Reviewed source: main 6002381d3832c35cdde1770bf665f276669396ef.

- grid_snapshots stores unique reading_timestamp, captured_at, generation MW,
  reporting counts, source name/URL, daily_json, disco_as_at, allocation totals,
  and raw_payload_json.
- genco_data and disco_data store snapshot-linked company/plant MW values and
  unique entity/snapshot pairs. These are potential longitudinal datasets.
- analytics_snapshots and distribution_intelligence_snapshots are computed
  outputs, not independent measurements. Transformer loading, state allocations,
  settlement growth, and risk scores must not be used as ground truth.
- Source timestamps are parsed from performance date and clock time in WAT when
  available; grid_monitor/utils/time.py falls back to fetched_at or the current
  collection time if parsing fails. Reading timestamps therefore need a basis
  audit against raw source fields before time-series research.
- get_history_points caps rows and returns older stored points when the requested
  window contains none. /api/history cannot by itself establish complete coverage
  or the presence of observations inside its advertised hours window.
- GenCo and DisCo observations may have different source times. A shared database
  snapshot ID does not prove simultaneous measurement.
- The collection configuration defaults to 30 minutes, but source updates,
  duplicate suppression, retries, and Render availability can alter cadence.
- The snapshot schema has no dedicated frequency series or customer interruption
  ledger. It cannot directly support frequency-compliance or SAIDI/SAIFI claims.
- No production database file or approved export is committed in the repository.
  This session has no authorized production database connection.

These are schema and implementation findings, not numerical findings about
Nigeria's electricity system.

## Bounded public audit

The validation workflow on this feature branch performs two sequential read-only
requests: /api/health and /api/history?hours=720&limit=2000. Responses have time and
size bounds. The log records timestamp coverage, invalid readings, missing values,
unexpected gaps, response hashes, and whether the row cap was reached. It does
not print database connection details or calculate generation outcomes.
A failure to fetch is reported explicitly and is not a zero-row database result.

The public sample cannot establish full historical company coverage, oldest
database records, source timestamp authenticity, station capacity, source rights,
or system outage causes. It is a readiness observation, not a research dataset.

## Reproduce the quality audit

~~~powershell
python -m pip install -r requirements-research.txt
python -m tools.research_data_audit public
~~~

An authorized operator can run database mode against a frozen export/read replica.
Set RESEARCH_DATABASE_URL securely in the operator's environment; do not paste
credentials into a PR, log, command example, or commit. Use a read-only database
role. This command uses a read-only transaction for PostgreSQL or query_only for
SQLite, projects scalar columns, streams generation rows, and never calls Flask
startup, migrations, the scraper, or the scheduler.

~~~powershell
python -m tools.research_data_audit database --expected-interval-seconds 1800
~~~

The expected interval is an explicit sampling assumption, not proof of source
cadence. A zero reading or collection gap is flagged for review, not called an
outage. The audit does not silently interpolate, fill missing values with zero,
convert observations to energy, or accept fallback timestamps as source time.

## Approval gates before any analysis

1. Obtain written source permission or an applicable licence covering analysis,
   publication of derived findings, and any proposed raw-data redistribution.
   Cite the specific terms and retain the evidence. Public visibility alone does
   not establish reuse rights; the NPD Terms page is not an upstream licence.
2. Assign actual authors, author order, contributions, and institutional details
   only with consent. An empty author field is not a licence to invent a byline.
3. Freeze the sampling window and export revision; record query, UTC boundaries,
   database snapshot time, row counts, SHA-256 file hashes, schema version, source
   URLs, collection configuration, and transformation code revision.
4. Audit missingness by day/entity, duplicate and irregular timestamps, source
   versus fetched timestamp basis, finite/nonnegative MW, source/collection lag,
   company name changes, and reconciliation of company totals. Retain exclusions
   and reasons. Never treat an absent record as zero or interpolate silently.
5. Have the authors approve inclusion/exclusion rules, cadence weighting,
   sensitivity checks, external event sources, and limitations before computing
   outcomes. Validate the research output independently of dashboard heuristics.
6. Review the draft findings, reproducibility materials, rights, PDF, and academic
   metadata. Only then create a completed record in grid_monitor/content/research.
   All three protocol drafts in this directory stay outside the public catalog.

## Research candidates

- generation-variability.md: observed generation variability and sampling effects.
- grid-reliability.md: separating collection gaps from candidate grid disturbances.
- distribution-allocation.md: allocation shares and concentration with timestamp alignment.

## Evidence needed from the operator/editor

A rights statement with supporting documents; an approved frozen database export
or read-only connection; the actual coverage/quality report; source timestamp
definitions; source-specific citation details; real authors; and editorial
approval. No publication date, DOI, or peer-review status has been assigned to
these protocols.
