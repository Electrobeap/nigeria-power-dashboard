# Observed generation variability and sampling effects in Nigeria's public grid readings

Status: unpublished study protocol and manuscript scaffold.
Authorship, affiliations, publication date, DOI, and peer-review credentials are unassigned.
Not approved for the public Research Library. Data reuse rights are unconfirmed.

## Draft abstract

This proposed study would characterize variability in source-reported grid generation while quantifying how collection coverage and timestamp handling affect interpretation. It would distinguish short-term changes from missing observations and compare results under predeclared sampling and completeness rules. No empirical result is presently reported: reuse rights, the analysis window, and a frozen dataset have not been approved.

## Research question

How much variation is visible within an approved period of source-reported generation, and how sensitive are the descriptive statistics to sampling gaps and timestamp fallback?

## Required evidence

GridSnapshot.reading_timestamp, captured_at, total_generation_mw, source, source_url, daily_json, as_at_time, and the relevant source timestamp evidence from raw_payload_json. Do not use moving averages from the public API as original observations.

Apply all gates in data-readiness-audit.md before calculating outcomes.

## Proposed methodology

1. Freeze an author-approved UTC window and preserve WAT labels for interpretation. Verify each source timestamp against performance_date and as_at_time; separate records whose timestamp was inferred from capture time.

2. Report coverage and missingness before variability. Inspect nonfinite and negative values, duplicates, long gaps, zero readings, and changes in source semantics. A zero is retained or excluded only after provenance review, with a logged reason.

3. For sufficiently observed windows, predeclare sample-based mean, median, standard deviation, interquartile range, and coefficient of variation (standard deviation divided by a positive mean). Compare sample-weighted and time-weighted summaries only when interval interpretation is justified.

4. Compute changes between successive valid observations only with their elapsed time. Express ramp rates as MW per elapsed hour and do not bridge long gaps as if adjacent observations were continuous telemetry.

5. Perform sensitivity analysis to the completeness threshold, permitted maximum gap, and inclusion of capture-time fallback records. Avoid filling missing readings or estimating MWh unless integration assumptions and coverage are explicitly defensible.

## Findings

Empirical findings pending. The repository confirms that generation and capture timestamps are stored, but it does not establish the actual research window, its completeness, or any variability result. No MW averages, volatility values, trend direction, or statistically significant differences are asserted.

## Limitations

Public dashboard readings can be delayed, revised, or sparsely sampled. Generation alone does not measure electricity delivered to every customer, unmet demand, installed availability, or outage causes. Deduplication of repeated source timestamps can create irregular intervals even when collection is operating normally.

## Reproducibility package

An immutable input manifest; exclusion log; interval/completeness table; generation series with visible gaps; predeclared variability tables and sensitivity plots only after approval; exact code/environment versions.

Use export-queries.sql on an authorized read-only frozen database; hash the export,
retain the query/window and exclusion decisions, and run tools/research_data_audit.py.
The quality audit is not the scientific analysis. Authors must approve the final
analysis code and its test cases before execution. Keep actual inputs and code
revisions with the manuscript; do not upload raw data where rights disallow it.

## References to verify and retain

1. NIGGRID 24-hour Grid Performance Dashboard: https://www.niggrid.org/Dashboard
2. Nigeria Power Data source timestamp implementation: grid_monitor/utils/time.py
3. Nigeria Power Data storage/query implementation: grid_monitor/services/storage.py
4. Nigeria Power Data methodology: https://nigeriapowerdata.com/methodology

Source links identify required evidence, not a claim that access confers reuse
rights. Final references must identify the exact dataset/document version and
access date actually used. Add no invented access or publication dates.
