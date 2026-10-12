# Coverage-aware analysis of reported DisCo allocation shares and concentration

Status: unpublished study protocol and manuscript scaffold.
Authorship, affiliations, publication date, DOI, and peer-review credentials are unassigned.
Not approved for the public Research Library. Data reuse rights are unconfirmed.

## Draft abstract

This proposed study would describe distribution-company allocation shares over an approved period, emphasizing observation completeness and the alignment of source timestamps. It would examine whether measured changes in allocation concentration persist after excluding incomplete reporting sets. It would not substitute regional estimates for actual allocations or equate bulk allocation with household service. No company ranking, concentration estimate, or geographic conclusion is presently reported.

## Research question

How do reported DisCo allocation shares vary over a verified observation window, and how much of the apparent change is attributable to missing company reports or asynchronous source times?

## Required evidence

DiscoData.company, load_allocation_mw, snapshot_id joined to GridSnapshot.disco_as_at, total_load_allocation_mw, reading_timestamp, captured_at, source_url, and source payload evidence. GenCo output may provide context only after source-time alignment; estimated state/transformer series are excluded from measured results.

Apply all gates in data-readiness-audit.md before calculating outcomes.

## Proposed methodology

1. Freeze the licensed export and documented company-name crosswalk. Preserve renamed entities and original labels rather than silently merging names. Establish the expected reporting set from source evidence for each period.

2. Parse DisCo-specific source time independently of the national generation timestamp. Exclude or separately report non-alignable snapshots. A foreign key to one GridSnapshot is not proof of simultaneity.

3. Audit absent, null, negative, and zero allocation values. Compare the sum of reported company MW with the published total using a preregistered tolerance consistent with source precision. Distinguish complete reporting sets from partial sets.

4. For complete valid sets, define company share as its reported MW divided by the sum of eligible company MW. Define HHI as the sum of squared shares, explicitly stating the 0-to-1 scale. Do not interpret missing-company shares as zero or report partial-set concentration as national concentration.

5. Compare descriptive distributions and within-company changes using a predeclared temporal weighting rule. Include sensitivity analyses for reporting-set completeness and timestamp tolerance. Discuss allocation constraints without inferring discrimination, technical losses, served population, or customer supply hours.

## Findings

Empirical findings pending. The schema supports snapshot-linked DisCo rows and a separate allocation timestamp, but company completeness, alignment accuracy, and licensed research coverage remain unverified. No DisCo performance ranking, HHI value, capacity deficit, or regional equity claim has been calculated.

## Limitations

Allocated power is not metered customer delivery or energy consumed. Snapshot rows may combine asynchronously scraped sources. Distribution constraints, embedded generation, and feeder-level outages are not fully represented. Geographic planning estimates cannot validate measured local service.

## Reproducibility package

Source-time and company-name audit; reporting-set completeness matrix; reconciliation/exclusion log; share/concentration methods; tables and charts generated only from the subsequently approved analysis set.

Use export-queries.sql on an authorized read-only frozen database; hash the export,
retain the query/window and exclusion decisions, and run tools/research_data_audit.py.
The quality audit is not the scientific analysis. Authors must approve the final
analysis code and its test cases before execution. Keep actual inputs and code
revisions with the manuscript; do not upload raw data where rights disallow it.

## References to verify and retain

1. NIGGRID DisCo load profile: https://www.niggrid.org/DisCoLoadProfile
2. Nigeria Power Data schema: grid_monitor/models.py
3. Nigeria Power Data snapshot construction: grid_monitor/services/storage.py
4. Nigeria Power Data data sources: https://nigeriapowerdata.com/data-sources

Source links identify required evidence, not a claim that access confers reuse
rights. Final references must identify the exact dataset/document version and
access date actually used. Add no invented access or publication dates.
