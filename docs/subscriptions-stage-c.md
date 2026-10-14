# Stage C: Paystack sandbox billing (review required)

This branch is not a production billing release. No deployment, merge, real charge,
production flag change, or USD collection is authorized. Community data and the
town/city Pro Preview remain public. The provisional Pro price is NGN 7,500/month;
USD 9/month remains display-only. Business/Enterprise remain Contact Sales.

## Architecture and trust boundaries

- Reuses Stage A users, immutable version-1 prices and UserSubscription contracts.
  Reuses Stage B authorization; no existing public route is gated.
- Four additive tables: billing_accounts, billing_payments, billing_invoices,
  billing_events. There are no foreign keys to energy tables.
- The server reserves one checkout per account before calling Paystack. It fetches
  the configured test plan and checks integration, domain, amount, currency and
  monthly interval. The browser cannot supply price, plan, currency or callback.
  Plan codes are configured, never fabricated or created automatically.
- Verified, active email identity and CSRF are required for checkout and management.
  Checkout retries resume the same URL, not another charge initialization. An
  uncertain initialization is retained for reconciliation/operator review.
- Callback GET only enqueues the owned reference. It does not grant access.
  The worker verifies the transaction through Paystack and matches amount,
  NGN currency, test domain, customer, transaction reference and account ownership.
  Initial subscription binding additionally matches the original authorization
  and creation time. Ambiguous matches fail closed.
- HMAC-SHA512 is checked over bounded raw webhook bytes before parsing. Only
  minimal billing fields are persisted, not cards, reusable authorization codes,
  API keys, raw bodies or subscription email tokens.
- Raw-body digests deduplicate delivery; unique transaction IDs/references and
  invoice codes prevent semantic replays. Paystack's documented signature has
  no timestamp-based freshness contract: we do NOT reject legitimate delayed
  events using an invented five-minute signature window. Old deliveries cannot
  extend periods; current provider verification and immutable payment periods
  are the authority.
- Webhook acknowledgement follows durable insertion. A separate billing worker
  performs external calls; no work is appended to the electricity scheduler.
  Database leases serialize events per account across processes. Failed attempts
  use bounded backoff and enter a review queue after 12 attempts.
- Recurring invoices must have valid monthly periods and successful server-verified
  transactions. Invoice creation or failure never grants a future period.
  Paid periods use explicit invoice dates, or the verified first paid timestamp
  and first provider next-payment date. We never grant now + 30 days.
- Cancel/non-renew notifications reconcile current provider status, preventing
  late events from undoing recovery. Paid access continues to its verified expiry.
  Attention/failed renewal does not create a grace entitlement.
- Sandbox entitlements require matching successful ledger evidence and are ignored
  if sandbox mode is disabled. Stage B premium flags still must be explicitly
  enabled in isolated staging. Legacy/manual non-Paystack contracts are unchanged.
- Account billing pages are private/no-store/noindex, have no GA/Clarity scripts,
  and use the existing account CSP. Public analytics/SEO integrations are untouched.

## Configuration

Production defaults remain:
```dotenv
PAYSTACK_TEST_CHECKOUT_ENABLED=false
LIVE_BILLING_ENABLED=false
USD_CHECKOUT_ENABLED=false
BILLING_ENVIRONMENT=disabled
PREMIUM_GATING_ENABLED=false
PRO_PREVIEW_ENABLED=true
```

For an explicitly approved, isolated staging environment only:
```dotenv
ACCOUNTS_ENABLED=true
SUBSCRIPTIONS_ENABLED=true
PAYSTACK_TEST_CHECKOUT_ENABLED=true
BILLING_ENVIRONMENT=staging
APP_BASE_URL=https://YOUR-APPROVED-STAGING-HOST
PAYSTACK_SANDBOX_ORIGIN=https://YOUR-APPROVED-STAGING-HOST
PAYSTACK_SECRET_KEY=<test secret from the company Paystack dashboard>
PAYSTACK_NGN_PRO_PLAN_CODE=<actual NGN monthly test plan code>
PAYSTACK_TEST_INTEGRATION_ID=<actual integration ID from Paystack>
LIVE_BILLING_ENABLED=false
USD_CHECKOUT_ENABLED=false
PRO_PREVIEW_ENABLED=true
SESSION_COOKIE_SECURE=true
AUTH_EMAIL_ENABLED=true
AUTH_EMAIL_VERIFICATION_REQUIRED=true
REQUIRE_DATABASE_ON_STARTUP=true
AUTO_CREATE_TABLES=false
RUN_MIGRATIONS_ON_STARTUP=false
HISTORY_CAPTURE_ENABLED=false
WEB_SCHEDULER_ENABLED=false
INDEXNOW_ENABLED=false
INDEXNOW_AUTO_NOTIFY_ENABLED=false
```

Also configure existing SECRET_KEY (32+ random characters), DATABASE_URL for a
**separate staging PostgreSQL database**, AUTH_SMTP_HOST/PORT/USERNAME/PASSWORD,
AUTH_MAIL_FROM, and existing account security options. Never use production data
or keys. Keep PREMIUM_GATING_ENABLED=false unless staging authorization tests
have been explicitly approved. No new secrets belong in Git, screenshots or logs.

Live keys, live billing, USD billing, mismatched origins, production domain and the
known production Render hostname are rejected at startup. Operator approval must
verify any additional host aliases and database isolation; configuration alone
cannot prove that a database is not production. Do not use a founder's personal
domiciliary account for corporate settlements.

## Paystack prerequisites and URLs

1. Company-controlled Paystack test account, test secret and integration ID.
2. A real test plan: NGN, amount 750000 minor units, interval monthly. Review it
   in Paystack before configuring its PLN_ code. Do not edit an existing plan's
   amount to silently change contracted pricing.
3. An approved HTTPS staging origin, verified-email test users and separate DB.
4. Test-mode webhook URL:
   `https://YOUR-APPROVED-STAGING-HOST/api/billing/paystack/webhook`.
5. Fixed callback:
   `https://YOUR-APPROVED-STAGING-HOST/billing/paystack/callback`.
   Callback fields from requests are rejected. Configure this URL in the test
   account where required; do not change production integration settings.
6. Use only Paystack's documented test cards. No real payment data is required.
7. Subscription management is a self-owned POST to the provider's documented
   management-link API. Links are not stored/logged. Recovery/payment-method
   updates are performed on the provider's page and reconciled afterward.

Supported events: charge.success, subscription.create, invoice.create,
invoice.update, invoice.payment_failed, subscription.not_renew,
subscription.disable. The adapter is separate from account/entitlement policy;
a future provider requires its own verified adapter and reviewed migration.

## Staging procedure

After code review and explicit approval, in a disposable staging environment:
```powershell
python -m pip install -r requirements-research.txt
python -m flask --app app db upgrade
python -m flask --app app seed-subscription-prices
python -m flask --app app billing-worker --once
python -m flask --app app billing-status
```

Run the web service with the existing Gunicorn entrypoint. Run a separate supervised
process for `python -m flask --app app billing-worker`; do not run it inside web
workers or change the grid scheduler. Billing CLI commands suppress unrelated
background-service startup; normal web startup is unchanged. A worker failure leaves acknowledged events
durably pending. `--once` is for manual staging checks, not continuous operation.

The worker periodically queues reconciliation and recovers its last five provider
invoices plus the most recent invoice. Older missed periods require replaying
genuine invoice events through the Paystack dashboard/support workflow; never
invent invoice periods or payment references. Verify provider payloads against
the actual test account before release, particularly invoice periods and initial
subscription association. Missing/contradictory fields fail closed for review.

Monitor `billing-status` counts and event age in the staging DB. Investigate
review rows without dumping sensitive data. Correct the cause, then:
```powershell
python -m flask --app app billing-retry <reviewed-event-digest>
```
This requeues the retained audit event; it does not delete ledger/idempotency rows.

Test initial purchase, failed card then recovery, callback closed/absent, duplicate
delivery, invoice renewal/failure, cancellation and provider-managed recovery.
Confirm Pro access stops at paid-through expiry, and all public routes still work.

## Validation

GitHub Actions runs the complete suite on SQLite and PostgreSQL 16, including
research, geography, account, Stage B authorization and Playwright browser tests.
The new suite uses synthetic provider doubles and blocks unexpected external
network calls. It covers prices/identity/CSRF, raw signatures, duplicate and
semantic replay, concurrent callbacks/workers, lease recovery, wrong currencies,
initial failures, renewal failures, out-of-order cancellation, expiry and migration
preservation. Actual Paystack end-to-end staging is a separate required sign-off.

Local disposable test commands:
```powershell
python -m pip install -r requirements-research.txt
python -m compileall -q app.py grid_monitor migrations tools tests
python -m playwright install chromium
python -m pytest -q tests/test_sandbox_billing.py
python -m pytest -q
# Repeat with a disposable PostgreSQL database, NEVER production:
$env:SUBSCRIPTION_TEST_DATABASE_URL="postgresql+psycopg://TEST_USER:TEST_PASSWORD@localhost:5432/npd_test"
python -m pytest -q
Remove-Item Env:SUBSCRIPTION_TEST_DATABASE_URL
```
The test suite creates and drops tables. Never point test configuration at real data.

## Migration and rollback

Revision e14c20261014 follows d13a20261013. It only creates four billing tables and
indexes. Account startup accepts either reviewed revision when billing is off;
enabled sandbox billing requires the new revision and columns. No energy rows,
existing account contracts or historical observations are rewritten.

Preferred rollback: stop the staging worker, disable PAYSTACK_TEST_CHECKOUT_ENABLED
and PREMIUM_GATING_ENABLED, keep LIVE_BILLING_ENABLED/USD_CHECKOUT_ENABLED false,
retain all tables and roll back application code. Stage B's older exact-revision
startup validator needs the documented compatibility patch or accounts disabled
when running against the newer schema. Do not stamp Alembic to conceal a mismatch.

Downgrade to d13a20261013 is allowed only if **all four billing tables are empty**.
It refuses to drop populated financial audit records. Back up staging data before
migration; energy and account tables are never dropped by this revision.
Do not use db.drop_all(), test commands or destructive SQL on deployment databases.

## Approval checklist and unresolved requirements

- [ ] Review code, migration, negative tests and CI results.
- [ ] Approve isolated staging host, DB, worker supervision and alert ownership.
- [ ] Supply actual company test key, integration ID and matching plan; verify payload contracts.
- [ ] Complete real Paystack sandbox end-to-end/replay/cancellation/recovery checks.
- [ ] Review customer terms, provisional pricing, tax/invoices, privacy and retention.
- [ ] Define refund/dispute/chargeback operations before any live billing release.
- [ ] Security review, backup/restore exercise and load/rate-limit review.
- [ ] Confirm commercial reuse rights for premium data (currently unconfirmed).
- [ ] Obtain corporate USD settlement and provider eligibility approval separately.
- [ ] Explicitly approve any future merge, deployment or entitlement activation.

No live-payment enablement path is provided. Refund/dispute automation, additional
payment providers and multiple concurrent subscription plans are outside this
sandbox release. Do not interpret automated mocks as provider certification.

## Official integration references

- [Paystack subscriptions](https://paystack.com/docs/payments/subscriptions/)
- [Subscription API](https://paystack.com/docs/api/subscription/)
- [Transaction API](https://paystack.com/docs/api/transaction/)
- [Plan API](https://paystack.com/docs/api/plan/)
- [Webhook authentication and delivery](https://paystack.com/docs/payments/webhooks/)
