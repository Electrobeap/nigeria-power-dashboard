# Article discovery and SEO audit

## Scope and evidence

Audited the ten records in grid_monitor/services/articles.py at main
6002381d3832c35cdde1770bf665f276669396ef. All established /articles/<slug>
URLs and the existing Nigeria Power Data Team byline are preserved.

Git evidence:
- 693c95a28c1d9d64dfe2d796dabe6517e7c2a1e3, 2026-07-15: all ten articles,
  their sections, FAQs, titles, descriptions, keywords, sources, and recorded
  published_at/updated_at dates were introduced.
- 91ebc5c0e5ccd515d12b2681b28af29ee129c4f7, 2026-07-17: added illustrations.
- 2f26e312aec26d1640d8dff8f92099d422937b34, 2026-07-23: changed images to
  photographs, attribution, and image metadata. No substantive body rewrite.

The recorded editorial dates remain 2026-07-15 for publication and content
modification. Repository history corroborates those content dates; it is not
proof of the exact first public deployment time. Image, navigation, or metadata
maintenance does not reset content dates. Do not replace them with today's date,
a deploy timestamp, or a guessed review date. Authors can supply corrections
supported by the editorial/deployment record. The article constructor now permits
per-article date values when genuine future editorial revisions warrant them.

## Ten-record inventory

Each row retains its original full title, description, route, category, and keywords.
All ten have distinct titles/descriptions, complete sections, FAQs, reference links,
responsive images with alt text, a visible team byline, and date metadata.

| Article slug | Topic/category | Contextual dashboard link |
| --- | --- | --- |
| understanding-nigerias-national-grid | Grid operations and supply chain | /#generation |
| how-electricity-is-generated-in-nigeria | Generation and capacity | /gencos |
| understanding-discos-and-gencos | Market roles | /#market-data |
| what-causes-grid-collapse | Grid operations and instability | /#generation |
| understanding-grid-frequency | Grid operations and frequency | /#generation |
| nigerias-electricity-market-explained | Market and settlement | /#market-data |
| role-of-tcn-in-power-transmission | Transmission | /geography |
| electricity-distribution-in-nigeria | Distribution | /discos |
| power-sector-reforms-explained | Policy | /states |
| reading-nigeria-power-data-dashboard | Data analysis | /#generation |

## Findings and changes

- Research was empty with no related educational resources. The library now has
  a clearly separate Related Energy Articles & Guides section. It links to the
  existing pages without copying their full bodies or inventing research records.
- Shared searches reuse the existing full-text article search (title, description,
  category, keywords, sections, and tables). A scholarly type filter applies only
  to research records. When no research is published, that fact remains visible
  even when guides match the search.
- Article HTML previously emitted Article microdata as well as JSON-LD. Removed
  the duplicate microdata representation; the existing JSON-LD graph remains.
- JSON-LD previously attributed article authorship to the platform organization
  while the visible byline said Nigeria Power Data Team. Each educational Article
  now uses an Organization author with that exact team name and /about URL.
  No named researchers, affiliations, or credentials are inferred.
- Article JSON-LD now includes its visible references and free-access status.
  Unrelated Dataset nodes are not attached to educational Article pages.
- Publication/modification dates use semantic time elements. Wide tables have
  captions, keyboard focus, and named scroll regions.
- Every guide links to /research, /methodology, /data-sources, and live dashboard
  sections. Methodology and Data Sources link back to relevant educational guides.
- Search/filter variants are noindex,follow. Unfiltered pagination has its own
  canonical URL, such as /articles?page=2, rather than incorrectly declaring page
  1 equivalent. Article URLs and the unfiltered research library remain indexable.
- Existing sitemap/IndexNow URL registration already includes all ten articles
  and eligible research records. Tests verify inclusion and crawler permissions.
- GA4, Clarity, social images, default styling, and geography routes are preserved.
  New guide cards use fixed 16:9 media, lazy loading, and responsive columns.

## Source and editorial limitations

The articles cite NIGGRID's dashboard, NERC, TCN, and NPD methodology. Those are
relevant public reference destinations, not evidence that every narrative claim
has been scientifically verified or independently peer reviewed. Several are
agency homepages rather than pinpoint documents. An editor should add dated,
claim-specific source documents when undertaking the next substantive review,
especially for institutional responsibilities, market reforms, and grid incidents.

Stock images are illustrative and are not evidence of a specific Nigerian asset.
Existing image credits/links are retained. External availability and licensing
must be checked as part of editorial maintenance.

No new legal, operational, numerical, or institutional claims were inserted into
the educational body text. These guides remain educational Article content,
never ScholarlyArticle content. The Research Library supports scholarly metadata
only for original publications that pass its existing approval gates.

## Validation

Automated tests cover all ten rendered article pages, metadata uniqueness,
author consistency, recorded dates, canonicals, Article-only typing, citations,
sitemap and robots permissions, contextual links, and geography regressions.
Browser tests exercise 1440, 768, 390, and 320 px layouts, card/media separation,
dark-mode dimensions, search interaction, document overflow, and JavaScript errors.
Third-party images and trackers are controlled in browser tests; this is not
a live Unsplash/GA4 availability test or a Lighthouse score claim.
