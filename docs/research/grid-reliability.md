# Separating collection gaps from candidate grid disturbances in public generation records

Status: unpublished study protocol and manuscript scaffold.
Authorship, affiliations, publication date, DOI, and peer-review credentials are unassigned.
Not approved for the public Research Library. Data reuse rights are unconfirmed.

## Draft abstract

This proposed study would evaluate which features of a public generation time series can flag candidate disturbances without confusing missing collection with loss of electricity supply. Source-reported changes would be cross-checked against independently documented system events. The work would report detection uncertainty rather than claim customer reliability from national generation alone. No event counts, outage durations, or reliability scores have been calculated.

## Research question

Which observed generation changes merit investigation, and what evidence is needed to distinguish a real system disturbance from stale data, collection gaps, or timestamp error?

## Required evidence

The approved generation export plus capture logs and source time evidence, independently sourced and licensed system-event reports, and any verified restoration records. Existing AnalyticsSnapshot.outage_json is a heuristic output, not an independent event label.

Apply all gates in data-readiness-audit.md before calculating outcomes.

## Proposed methodology

1. Build a missingness map using source and capture timestamps. Mark delayed, repeated, out-of-window, and timestamp-fallback observations separately. Do not label absent snapshots as outages.

2. Before outcome analysis, preregister an event-screening rule, maximum inter-reading gap, minimum coverage, and external event matching window. Record why thresholds were chosen and test sensitivity without optimizing against reported outcomes.

3. Flag candidate drops only between valid, sufficiently close observations. Preserve the original MW readings, elapsed time, and provenance. Do not infer an exact start or restoration time between sparse samples.

4. Create an independently reviewed event ledger from identifiable official reports with URLs, event times/timezones, document versions, and usage permissions. Classify candidates as corroborated, contradicted, or unresolved.

5. If an adequate independent ledger exists, estimate agreement and detection limitations. Otherwise publish only a method and data-quality study, not a validated outage detector. Do not compute SAIDI, SAIFI, or frequency-compliance measures without the necessary customer/frequency data.

## Findings

Empirical findings pending. The repository stores collection and source-time fields, while the normalized schema has no dedicated customer interruption ledger or frequency time series. That establishes a measurement limitation, not a conclusion about grid reliability. No grid collapse, causal mechanism, duration, or failure rate is inferred.

## Limitations

Rapid disturbances can occur between samples. Source websites and collectors can fail independently of the grid. Event reports can be incomplete or use different geographic definitions. A national generation dip does not prove a total collapse or identify a technical cause.

## Reproducibility package

A reviewed time-alignment specification; collection-gap map; transparent event-screening code; evidence-linked event ledger if licensed; candidate versus corroborated event table; uncertainty and unresolved-event notes.

Use export-queries.sql on an authorized read-only frozen database; hash the export,
retain the query/window and exclusion decisions, and run tools/research_data_audit.py.
The quality audit is not the scientific analysis. Authors must approve the final
analysis code and its test cases before execution. Keep actual inputs and code
revisions with the manuscript; do not upload raw data where rights disallow it.

## References to verify and retain

1. NIGGRID source readings: https://www.niggrid.org/Dashboard
2. Nigerian Electricity Regulatory Commission report portal: https://nerc.gov.ng/ (select exact dated event documents before analysis)
3. Nigeria Power Data analytics implementation: grid_monitor/services/analytics.py
4. Nigeria Power Data methodology: https://nigeriapowerdata.com/methodology

Source links identify required evidence, not a claim that access confers reuse
rights. Final references must identify the exact dataset/document version and
access date actually used. Add no invented access or publication dates.
