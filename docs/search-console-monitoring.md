# Manual search discovery monitoring

## Google Search Console

Use the verified nigeriapowerdata.com property. An authorized owner must perform
these steps; this feature does not access an account or submit URLs automatically.

1. After an approved deployment, open Sitemaps and submit
   https://nigeriapowerdata.com/sitemap.xml. Check the fetch result and last read.
   Confirm all ten original /articles/ URLs and /research are present. Original
   research URLs appear only after actual author-approved publication.
2. Inspect /research, representative articles, /articles?page=2, and (when
   published) each original paper URL. In URL Inspection, compare the indexed
   result with Test Live URL. Check HTTP success, crawl and indexing permission,
   rendered content, resources, and the declared canonical.
3. Compare the Google-selected canonical in the indexed report. A live test
   cannot predict canonical selection. For eligible newly published or corrected
   pages, request indexing. A request does not guarantee inclusion or timing.
4. Use Page indexing to investigate exclusions: accidental noindex, blocked
   crawling, duplicate canonical selection, redirect errors, soft 404s, and server
   failures. Internal search variants are intentionally noindex,follow.
5. In Performance / Search results, enable clicks, impressions, CTR, and average
   position. Filter pages by /articles/ and /research separately; inspect queries
   including electricity, grid, and distribution. Compare equal date windows and
   segment by device/country where useful.
6. Record the observation date, reporting window, page group, query filters,
   clicks, impressions, CTR, average position, and indexing observations in the
   editorial tracking sheet. Export the report for evidence; do not enter invented
   baseline numbers. Compare weekly after release and monthly thereafter.
7. Review Core Web Vitals/mobile page experience and structured-data reports when
   available. Test affected article URLs in Rich Results Test. A successful
   markup test is not proof of ranking, scientific validity, or Scholar indexing.

When diagnosing a regression, first check production HTTP errors and the rendered
canonical/noindex values, then compare deployment dates against the report window.
Avoid resetting article dates to stimulate crawling.

## Google Scholar

The Research Library is a discovery hub, but only actual scholarly papers should
carry citation_* metadata and ScholarlyArticle. Educational guides remain Article
content at their existing URLs. Once real papers have author/editorial approval:
verify their stable HTML abstract page, real author order, publication date,
accessible searchable PDF, citation_pdf_url, version, references, and crawl access.
Search Scholar for each exact title after allowing time for discovery. Scholar
has no equivalent guarantee from Google Search Console URL inspection.

## Zenodo and ResearchGate

Follow docs/research-publishing.md. Deposit approved work manually on Zenodo;
verify the actual registered version DOI before displaying it. Authors may use
the existing /research/<slug>/submission.json metadata export for their own
ResearchGate submissions, subject to sharing rights. No automatic listing,
indexing, deposit, peer review, or repository acceptance is represented.

## Official guidance

- Sitemaps report: https://support.google.com/webmasters/answer/7451001
- URL Inspection: https://support.google.com/webmasters/answer/9012289
- Performance report: https://support.google.com/webmasters/answer/7576553
- Article metadata: https://developers.google.com/search/docs/appearance/structured-data/article
- Date guidance: https://developers.google.com/search/docs/appearance/publication-dates
- Scholar inclusion: https://scholar.google.com/intl/en/scholar/inclusion.html
