# Stage D1: offline subscription lifecycle validation

## Scope and safety

This stage adds tests, not a payment mode. The production Flask code, routes,
prices, migrations, billing settings and deployed subscription records are
unchanged. All HTTP payment responses come from synthetic fixtures in `tests/`.
There is no environment variable, public route or application configuration that
selects a mock provider. The normal provider factory continues to return Paystack.

Tests use a fixed UTC accounting clock (15 January 2026 at 12:00 UTC), synthetic
identities and credentials, local disposable databases, and real application
authentication, CSRF, webhook HMAC verification, billing worker, payment ledger,
premium guards and API loaders. Browser/thread timeout clocks are not frozen.
Generated checkout references remain random; assertions do not depend on them.

The real Paystack adapter runs against a test-only requests transport that checks
the API origin, server-owned pricing, fixed callback, timeout, TLS origin and
no-redirect options. Any unexpected HTTP call fails. The browser test captures the application's checkout POST with redirects disabled,
asserts the real allowlisted 303, and substitutes a local checkout page. It never
visits Paystack; redirect chains cannot escape the test interception. No activated provider account or
genuine key is needed.

**Never run this suite against production or a copy that must be retained.**
Fixtures create/drop tables. With no override, tests use temporary/in-memory
SQLite. A global pytest guard rejects `SUBSCRIPTION_TEST_DATABASE_URL` unless it
identifies local PostgreSQL, with username and database both `npd_test`, and no
URL options. The guard cannot distinguish a production database forwarded onto
localhost: use a disposable container, never a tunnel to real data.

## Coverage

- Community and anonymous requests denied for additive premium analytics/exports;
  verified Pro can retrieve real synthetic-data aggregates and CSV through GET/HEAD.
- Checkout initialization, callback and even an authentic webhook do not grant
  access until the worker confirms the transaction with the provider adapter.
- Server-controlled NGN 750,000 kobo price, monthly plan and callback remain enforced.
- Failed/abandoned initial payments, provider outage/backoff, verified recovery.
- Renewal success, failed invoice, paid-period boundary, delayed notifications and
  recovery without duplicate credits.
- Cancellation stops renewal but retains the already-paid period; expiry is
  end-exclusive and downgrades entitlements to Community without deleting history.
- Provider recovery alone never grants an unpaid new period.
- Revoked identities/sessions, reversed payments and disabled sandbox billing
  invalidate access even when the analytics cache is warm.
- Exact raw-body HMAC, wrong keys, modified bytes, invalid JSON, concurrent callbacks,
  duplicate byte payloads, semantically identical payloads and old payment replays.
- State/regional routes, research, articles, sitemap, public historical views and
  planning-grade town preview remain accessible; energy observations stay unchanged.
- Browser checkout, activation, cancellation and expiry; desktop/tablet/mobile
  billing layout, overflow and console checks, with external networking blocked.
- Production-host startup guards, unchanged real provider factory, no application
  imports from tests, and disposable-database safeguards.

The complete Stage A/B/C suite still runs, including account recovery, CSRF,
throttling, migration safety, payment association, worker leases and geography,
research, SEO and browser regressions. Shared Stage C helpers were moved to
`tests/billing_support.py`; their existing tests and scenarios are retained.

## Run on Windows 11

Use a clean development checkout and a virtual environment. Do not load a
production `.env`. No real payment secrets belong in this process.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-test.txt
$env:HISTORY_CAPTURE_ENABLED = "false"
$env:WEB_SCHEDULER_ENABLED = "false"
$env:INDEXNOW_ENABLED = "false"
$env:INDEXNOW_AUTO_NOTIFY_ENABLED = "false"
$env:RUN_MIGRATIONS_ON_STARTUP = "false"
$env:ACCOUNTS_ENABLED = "false"
$env:SUBSCRIPTIONS_ENABLED = "false"
$env:PREMIUM_GATING_ENABLED = "false"
$env:PAYSTACK_TEST_CHECKOUT_ENABLED = "false"
$env:LIVE_BILLING_ENABLED = "false"
$env:USD_CHECKOUT_ENABLED = "false"
$env:PRO_PREVIEW_ENABLED = "true"
Remove-Item Env:SUBSCRIPTION_TEST_DATABASE_URL -ErrorAction SilentlyContinue

python -m pip check
python -m compileall -q app.py grid_monitor migrations tools tests
python -m ruff check --select E9,F tests/billing_support.py tests/billing_transport.py tests/test_subscription_lifecycle.py tests/test_testing_safety.py
python -m mypy --strict --follow-imports=skip tests/billing_transport.py
python -m tools.research_publications validate
python -m playwright install chromium
python -m pytest -q tests/test_subscription_lifecycle.py tests/test_sandbox_billing.py tests/test_premium_authorization.py tests/test_testing_safety.py
python -m pytest -q --junitxml=test-results/sqlite.xml
```

For PostgreSQL, run a disposable PostgreSQL 16 container. This creates no external
service or production connection:

```powershell
docker run --name npd-d1-postgres --rm -d -p 127.0.0.1:55432:5432 -e POSTGRES_USER=npd_test -e POSTGRES_PASSWORD=test-only-password -e POSTGRES_DB=npd_test postgres:16
docker exec npd-d1-postgres pg_isready -U npd_test
$env:SUBSCRIPTION_TEST_DATABASE_URL = "postgresql+psycopg://npd_test:test-only-password@127.0.0.1:55432/npd_test"
python -m pytest -q --junitxml=test-results/postgres.xml
docker stop npd-d1-postgres
Remove-Item Env:SUBSCRIPTION_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Wait for `pg_isready` to report accepting connections before pytest.
Run the suite serially against one database, not pytest-xdist with shared tables.

## CI and build scope

The subscription GitHub Actions workflow runs the entire suite on SQLite and
PostgreSQL 16, including Chromium, syntax compilation and research validation.
It checks installed dependencies and uploads JUnit results for each matrix job.
Ruff checks fatal/undefined/unused-name errors in the new/shared test code;
strict mypy checks the typed HTTP transport. These are scoped checks, not a claim
that the entire existing application is statically typed or lint-clean.

There is no separate frontend bundling/build stage in this Flask/Jinja project.
Python compilation, application startup in fixtures, template rendering,
dependency checks and browser regressions provide the available build validation.

## Limitations and genuine sandbox prerequisites

Synthetic fixtures prove the application's behavior against specified response
contracts, not Paystack account eligibility, actual provider API behavior, payment
settlement, real renewal timing or live webhook delivery. HMAC authenticates raw
bodies but has no signed freshness timestamp in this integration: replay safety is
provided by durable event deduplication, verified provider state, unique payments
and immutable paid periods, not a fabricated webhook timestamp.

Before genuine sandbox testing, obtain approval for a separate HTTPS staging
origin and isolated staging database/worker, a Paystack test account/integration
and an actual NGN monthly plan for 750,000 kobo. Configure the test-only secret,
plan and integration identifiers via environment variables, register the staging
callback and webhook, run reviewed migrations and explicitly seed pricing.
Follow [Stage C setup and rollback](subscriptions-stage-c.md). Validate real
checkout, first charge, invoice timing, renewal failure, cancel/re-enable behavior,
webhook retries and the provider's response shapes before any release approval.

Keep `LIVE_BILLING_ENABLED=false`, `USD_CHECKOUT_ENABLED=false` and
`PRO_PREVIEW_ENABLED=true`. Production checkout and premium flags remain unchanged.
Do not infer production readiness for financial collection from mock test success.
Corporate eligibility, settlement, taxes/refunds, customer terms and operational
monitoring still need commercial/security review.

No merge, deployment, migration execution on production, or billing activation is
authorized by this stage. Reverting this test-only PR requires no database rollback.
