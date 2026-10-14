# Stage B: additive premium authorization (draft, not activated)

Base: main e101fa1734af16bb72d9f4d3321b91466121551d, following merged Stage A PR #8.
Branch: feature/pro-entitlement-guards-20261014.

## Scope and release safety

This stage installs server-side guards on NEW /api/pro/ routes only.
No existing public route, free historical window, exportVisibleCsv behavior,
geographic calculation, research record, SEO tag, scheduler or energy model is
changed. No payment implementation or database migration is introduced.

Default flags remain:
~~~
ACCOUNTS_ENABLED=false
SUBSCRIPTIONS_ENABLED=false
PREMIUM_GATING_ENABLED=false
PRO_PREVIEW_ENABLED=true
PAYSTACK_TEST_CHECKOUT_ENABLED=false
USD_CHECKOUT_ENABLED=false
LIVE_BILLING_ENABLED=false
~~~

Existing deployment account settings are not changed by this branch.
All three account/subscription/gating flags must be explicitly true to expose
the new premium namespace. Otherwise it returns 404 before analytics/cache work.
Turning on PREMIUM_GATING_ENABLED without both prerequisites fails startup.
Payment flags still fail startup if enabled: sandbox checkout is a later stage.

No merge, deployment or flag changes are authorized by this PR.

## Endpoints

| Endpoint | Capability | Authorization when explicitly enabled |
| --- | --- | --- |
| GET /api/pro/generation-analysis | extended_history | Verified active account with paid-through Pro |
| GET /api/pro/exports/generation.csv | advanced_exports | Same Pro requirements, checked independently |
| GET /api/pro/towns/<slug> | town_intelligence | Anonymous public preview while PRO_PREVIEW_ENABLED=true; otherwise same Pro requirements |

HEAD uses the same guards. Unsupported methods and invented URL suffixes do not
produce reports. OPTIONS never contains premium data.
All responses in /api/pro/ (including errors and unknown paths) are private,
no-store, noindex, Vary: Cookie, with no permissive CORS or compression.
Requests are same-origin session authenticated; no API keys/tier headers or
user-supplied identity fields are trusted.

The towns endpoint is a future authorization boundary for planning intelligence,
not a claim that its current metrics are exclusive. Existing /api/geography/
town, parent, child and search responses remain public with their existing
fields even if this new endpoint's preview is disabled. Future exclusive town
metrics must be additive and confined to a guarded service. Do not copy those
new metrics into legacy parent/search/SEO payloads or static datasets.

## Identity and expiry

The centralized policy denies unknown capabilities. New premium routes do not
fall open when a flag is disabled.
Authentication comes from the Stage A signed session and database user loader.
Pro requires a currently active account, verified email (even when optional for
Community login), plan=pro, a started period and a definite future paid-through
end. Pending, past_due, expired, future-starting and missing-expiry contracts
do not qualify. Cancelled contracts retain access only until their existing
paid-through end; no renewal is implied. Both currency contracts are supported;
this does not enable USD checkout.

Account status, verification and subscription validity are rechecked in the DB
on every request BEFORE reading a report cache. No entitlement decision is
cached. Disabling an account, revoking its session or expiring its subscription
blocks the next request even when another Pro user warmed the data cache.
DB failures fail closed with sanitized 503 responses (identity-loader failures
may instead be treated as unauthenticated). No user/provider/SQL details leak.

401 = authentication_required; 403 = verification_required or
subscription_required; 404 = feature_unavailable; 400 = invalid_query;
503 = authorization_unavailable or data_unavailable.
The response includes a timestamp and safe /login and /pricing links.

## Daily generation analysis and CSV

Only start and end query parameters are supported. Both are strict YYYY-MM-DD
UTC dates; start is inclusive, end exclusive. Omit both for the previous 30
complete UTC calendar days. Range is bounded to 1-1827 days; end cannot exceed
tomorrow's UTC date. Requesting today is allowed and marked calendar_day_elapsed
false. Unknown/duplicate parameters, malformed dates, reversed/oversize ranges,
NaN/infinity and future-only requests are rejected. There is no arbitrary
column, SQL, format, user_id, role, currency, limit or callback parameter.

Examples after explicit staging approval and authenticated Pro login:
~~~
/api/pro/generation-analysis?start=2024-01-01&end=2024-02-01
/api/pro/exports/generation.csv?start=2024-01-01&end=2024-02-01
~~~

The new product provides:
- Daily count, sample mean, minimum, maximum and range.
- Change between adjacent observed calendar days.
- Seven-consecutive-day equal-weight mean; null when any day is missing.
- Standard deviation across observed daily means, not intraday volatility.
- Peak/lowest observed generation and explicit data-coverage metadata.
- A matching daily CSV with fixed date/numeric/boolean fields.

These are derived from stored source observations, not new verified measurements
or a household reliability measure. Arithmetic sample means are not energy MWh
or time-weighted daily output. Missing observations are not outages or zero
generation. Negative/null/non-finite readings are excluded and counted, never
deleted or altered. Empty periods return null values and zero observation counts.
Sampling density/completeness is disclosed rather than fabricated.
Provenance includes up to 50 distinct source/name URL pairs with a truncation
indicator. Original source data is not independently verified by this feature.

SQL selects scalar aggregates grouped by UTC date and uses the existing timestamp
index. It never loads raw_payload_json, ORM snapshots or related GenCo/DisCo
graphs. At most 1827 daily rows enter application memory. Two bounded read queries
produce a report: daily aggregates and distinct source references. The existing
bounded LRU holds identity-free reports for 30 seconds, namespaced by app/range.
calculated_at discloses cache age; entitlement checks always precede cache hits.
CSV is generated from the same report and uses only fixed numeric/date columns,
so source text cannot inject spreadsheet formulas or attachment filenames.

The historical data rights remain UNCONFIRMED. No commercial export activation
is authorized. Review data redistribution/reuse rights and report methodology
before making these services available, even for manual complimentary accounts.

## Tests and operational validation

GitHub Actions runs the full pytest suite twice, SQLite and PostgreSQL 16, along
with Python compileall, strict research catalog validation and browser tests.
The shared existing fixtures now honor the isolated PostgreSQL test URL, so
geography and research regressions also exercise PostgreSQL where they use the
shared database. Tests intentionally tied to SQLite behavior remain SQLite.
Never set SUBSCRIPTION_TEST_DATABASE_URL to production: fixtures DROP tables.

The new tests cover:
- Anonymous, Community, verified Pro, USD Pro, cancelled paid-through, expired,
  pending, past_due, future-starting, unverified, disabled and no-expiry accounts.
- GET/HEAD, direct CSV requests, forged identity/query values and parameter pollution.
- Warm-cache cross-user access and immediate revocation/expiry/verification changes.
- Fail-closed authorization/data failures with private, sanitized error responses.
- Preview on/off, preserved legacy town access and unavailable default endpoints.
- Numeric accuracy, half-open UTC windows, gaps, invalid readings, empty periods,
  CSV consistency/formula safety, bounded output/projections and no energy writes.
- Existing 8760-hour free history, public geography, research, articles, sitemap
  and scheduler/payment defaults. Existing full regressions remain in the suite.

Windows, using a disposable test database:
~~~powershell
git fetch origin
git switch feature/pro-entitlement-guards-20261014
python -m pip install -r requirements-research.txt
python -m playwright install chromium
$env:HISTORY_CAPTURE_ENABLED = "false"
$env:WEB_SCHEDULER_ENABLED = "false"
$env:INDEXNOW_ENABLED = "false"
$env:RUN_MIGRATIONS_ON_STARTUP = "false"
$env:ACCOUNTS_ENABLED = "false"
$env:SUBSCRIPTIONS_ENABLED = "false"
$env:PREMIUM_GATING_ENABLED = "false"
python -m compileall -q app.py grid_monitor migrations tools tests
python -m pytest -q
~~~

## Approval checklist before any release

- Review and approve this draft's code and successful CI; do not auto-merge.
- Approve data reuse/redistribution rights and methodology for commercial reports.
- Validate actual staging source coverage, indexed-query latency and concurrent
  export load against a production-sized sanitized database. Synthetic tests do
  not establish production latency or data completeness.
- Confirm Stage A migration, secure sessions, verification delivery, recovery,
  trusted proxy configuration and account abuse monitoring in staging.
- Approve explicit enablement of accounts/subscriptions/new premium services.
  Existing public routes must remain unaffected.
- Keep PRO_PREVIEW_ENABLED=true until a separate reviewed decision. Do not use
  waiver removal to take away already-public legacy geographic data.
- Implement authenticated Paystack NGN sandbox billing in a separate stage with
  server-controlled prices, fixed callbacks, signed webhooks and idempotency.
  No live or USD collection; no founder personal settlement accounts.
- Add product UI and a broader export UX in later work; this stage exposes
  additive API capabilities, not a redesigned dashboard.

Security reference: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
SQL aggregation reference: https://docs.sqlalchemy.org/en/20/tutorial/data_select.html
