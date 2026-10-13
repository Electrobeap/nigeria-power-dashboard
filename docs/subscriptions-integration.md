# Subscription integration: Stage 1 (draft review)

Base: main 0133f534301afa9d873b4274745c915e662656c9.
Source inspected without modification: feature/free-pro-subscriptions-20261011,
e5cf11947c433155aded03e3d1b33269a1a610f7.
Working branch: feature/subscriptions-integration-20261013.

## Reviewable stages

1. **This PR:** account security, manual dual-currency pricing, additive account
   tables, read-only entitlement decisions, preview semantics, route audit and tests.
2. **Separate PR:** server-side authorization before queries/caches, route aliases,
   hierarchy child/search results, advanced exports, and approved public baselines.
3. **Separate PR:** authenticated NGN Paystack sandbox checkout, fixed callbacks,
   server-verified transactions, HMAC webhooks, idempotency, renewals, expiry,
   cancellations and reconciliation. No live billing in any current stage.

Stage 1 does not claim to protect premium endpoints or process payments.
PREMIUM_GATING_ENABLED, PAYSTACK_TEST_CHECKOUT_ENABLED, USD_CHECKOUT_ENABLED and
LIVE_BILLING_ENABLED must stay false; attempting to activate them fails startup
explicitly instead of silently exposing an unfinished payment/gating system.
SUBSCRIPTIONS_ENABLED is false and cannot install guards by itself.
All existing historical views remain public, including longer ranges already
exposed by the current APIs. The proposed seven-day boundary is NOT activated.

## Selective integration

Reused/adapted from the old branch: independent currency price configuration,
integer minor units, versioned prices, subscription status/paid-through fields,
provider-reference boundary, and a centralized entitlement service.

Not copied: geography routes/queries/templates/scripts, navigation replacement,
old fixtures/tests, obsolete research code, broad models.py replacement,
c7d8e9f0a123 migration, payment/invoice/webhook payload tables or provider clients.

Fixed design issues found in the source:
- An unauthenticated checkout accepted email/callback from the request.
- Provider base URLs and callbacks could be supplied without a fixed trusted
  settlement/callback policy. Payment methods are deliberately absent in Stage 1.
- Pricing seeds rewrote existing versions and ran at startup.
- Entitlement code could compare naive SQLite timestamps to aware UTC values,
  and accepted subscriptions without a definite paid-through date.
- Pricing called the current keyword-only social metadata helper positionally.
- Business pricing was displayed as a purchasable figure; it now says Contact Sales.

Production geography/research code and fixtures are retained from main. The only
web.py changes are factual account/privacy/preview disclosures, not routing or
analytics calculations. The source branch remains unchanged.

## Prices and public access

| Plan | NGN | USD | Checkout |
| --- | --- | --- | --- |
| Community | Free | Free | No payment |
| Pro | 7,500/month (750000 minor units) | 9/month (900 minor units) | Coming Soon |
| Business | Contact Sales | Contact Sales | None |
| Enterprise | Contact Sales | Contact Sales | None |

Prices are provisional and independent of exchange rates. URL-based NGN/USD
selection is explicit; IP geolocation never picks a charge currency.
No environment setting can activate USD or live checkout in this stage.
Company settlement must use approved corporate arrangements, never the founder's
personal domiciliary account. No banking details or provider keys are requested.

National, regional, state, current public historical views, articles, eligible
research abstracts/PDFs and existing APIs are unchanged. PRO_PREVIEW_ENABLED=true
records the public town/city preview waiver. Turning it off alone does not install
a paywall. Planning intelligence must not be represented as metered observations.

## Accounts and security

Routes: /register, /login, POST /logout, /account, /forgot-password,
/reset-password, /resend-verification, /verify-email. All return 404 when
ACCOUNTS_ENABLED=false. /pricing and /api/subscriptions/pricing are public.
Auth/account routes are noindex and omitted from sitemap; pricing is included.

- Flask-Login and signed sessions with random server-held alternative user IDs.
- Scrypt N=32768, r=8, p=3; 15-128 character passwords with byte bounds.
- Flask-WTF CSRF checks on every account POST, including login/logout and tokens.
  Existing machine APIs (including IndexNow) are not globally CSRF-wrapped.
- Default Secure, HttpOnly, SameSite=Lax session cookies; absolute eight-hour
  login lifetime. Password reset and logout revoke all sessions for that account.
- Shared PostgreSQL/SQLite atomic rate counters, with both IP and normalized
  email budgets. Counters store keyed hashes, not plaintext identifiers.
- 30 IP attempts per action per 15-minute bucket; eight attempts per email
  per action. The fixed-window design can allow bursts near a window boundary.
- Do not enable proxy-header trust until the hosting edge's exact trusted proxy
  chain is verified. AUTH_TRUST_PROXY_HOPS=0 ignores client-supplied forwarding
  headers. Shared reverse-proxy addresses may need a reviewed configuration.
- Account responses are private/no-store, uncompressed, frame-blocked, with
  no-referrer and a restrictive self-only CSP. Auth pages have no GA4, Clarity,
  advertising, or third-party JavaScript. Public analytics integrations remain.
- Reset/verification tokens are random, hashed at rest, expiring and single-use.
  Email URLs use a fragment so the token is not sent in request URLs/logs;
  local JS transfers it to the POST form and clears it from browser history.
  GET never consumes a token, avoiding email-scanner side effects.
- Reset tokens expire in 30 minutes; verification tokens in 24 hours.
  New tokens replace old same-purpose links. A password change invalidates all
  outstanding tokens. No token, password or full provider error is logged.
- Registration and recovery use generic responses; all new accounts are Community
  regardless of submitted role/plan/price fields. No API exposes another account.

## Email operations

AUTH_EMAIL_ENABLED uses SMTP with mandatory STARTTLS and certificate validation.
Delivery runs in a bounded single-worker queue per process (20 outstanding jobs),
not the grid scheduler. Requests enqueue the same work for known/unknown
addresses; account existence and mail errors are not disclosed in responses.

This queue is intentionally not a durable mail-delivery service. A worker restart,
free-tier sleep or SMTP outage may lose pending delivery; users can request a new
link. Monitor account_email_delivery_failed and test end-to-end delivery before
signup approval. A durable outbox/provider integration is a follow-up if required.
SMTP errors log only their exception type, never connection secrets or addresses.
No production SMTP credentials were provided or tested in CI.

AUTH_EMAIL_VERIFICATION_REQUIRED defaults true. Enabling accounts with required
verification but disabled delivery is rejected. Optional verification is possible
only by explicitly disabling that requirement. Do not approve public signup
without verified mail deliverability, recovery, abuse monitoring and policies.

## Migration safety

New revision d13a20261013 follows the deployed a91b2c3d4e5f6 head and only creates:
users, subscription_plan_prices, user_subscriptions, account_tokens,
auth_rate_limits. There are no foreign keys to energy tables and no ALTER,
UPDATE, DELETE or DROP statements against grid observations.

The older development migration c7d8e9f0a123 is NOT imported. If a test database has
that revision, do not stamp or reuse it blindly; create a separate disposable
test database or plan an explicit reviewed schema reconciliation.

The existing startup fallback that stamped head after duplicate/missing-revision
errors is removed. Failed migrations remain failures; nothing is falsely marked
applied. Existing REQUIRE_DATABASE_ON_STARTUP behavior still controls whether
public-only startup can continue. Production account activation additionally
requires all account columns and the reviewed migration revision to exist.

Rollback is non-destructive: disable flags and revert application code while
retaining account and energy tables. The new migration deliberately refuses a
destructive downgrade. Back up and restore-test the database before approval.

Prices are seeded by an explicit CLI command, not during startup/requests.
The command inserts missing versioned rows, rejects conflicts and never updates
existing subscription contracts. A price change needs a new reviewed version.

## Environment

Keep the following values for this unapproved stage:
~~~
ACCOUNTS_ENABLED=false
SUBSCRIPTIONS_ENABLED=false
PREMIUM_GATING_ENABLED=false
PRO_PREVIEW_ENABLED=true
PAYSTACK_TEST_CHECKOUT_ENABLED=false
LIVE_BILLING_ENABLED=false
USD_CHECKOUT_ENABLED=false
SESSION_COOKIE_SECURE=true
AUTH_EMAIL_ENABLED=false
AUTH_EMAIL_VERIFICATION_REQUIRED=true
AUTH_TRUST_PROXY_HOPS=0
~~~

When account-only staging is explicitly approved: set a randomly generated
SECRET_KEY (32+ characters), the correct HTTPS APP_BASE_URL, SMTP host/port
(default 587), AUTH_MAIL_FROM and provider-issued SMTP username/password in the
hosting secret store. Enable AUTH_EMAIL_ENABLED and ACCOUNTS_ENABLED only there.
No secrets belong in Git, PRs, logs or test fixtures. Public signup approval is
separate from code review. There is no Paystack key requirement in Stage 1.

## Windows validation (disposable local database only)

~~~powershell
git fetch origin
git switch feature/subscriptions-integration-20261013
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-research.txt
python -m playwright install chromium
$env:HISTORY_CAPTURE_ENABLED = "false"
$env:INDEXNOW_ENABLED = "false"
$env:RUN_MIGRATIONS_ON_STARTUP = "false"
python -m compileall -q app.py grid_monitor migrations tools tests
python -m pytest -q
~~~

Never point SUBSCRIPTION_TEST_DATABASE_URL at production: the opt-in PostgreSQL
test fixture creates/drops all tables in that **disposable** database.
GitHub Actions supplies an isolated PostgreSQL 16 service and runs the complete
available suite in SQLite and PostgreSQL account/migration configurations.
Existing research/geography fixtures continue using their original SQLite setup.

After backup and manual staging approval, with accounts and grid collection off:
~~~powershell
$env:AUTO_CREATE_TABLES = "false"
$env:RUN_MIGRATIONS_ON_STARTUP = "false"
python -m flask --app app db current
python -m flask --app app db upgrade
python -m flask --app app db current
python -m flask --app app seed-subscription-prices
~~~

Confirm revision d13a20261013, observation counts/samples, schema and mail tests.
Never use stamp to hide migration errors. Do not automatically merge/deploy.
Render service configuration is not modified in this PR.

## Outstanding approvals

- Stage 2 route enforcement and export design from subscription-access-audit.md.
- Stage 3 Paystack test-plan amount/currency verification, fixed callbacks,
  authenticated checkout, HMAC webhooks, idempotency/concurrency, paid-through,
  cancellation, replay/out-of-order events, refund and dispute policies.
- Corporate NGN onboarding; corporate USD settlement/provider eligibility later.
- Source redistribution/monetization rights, which remain unconfirmed.
- Legal/editorial review of account privacy, retention/deletion and paid terms.
- Staging SMTP delivery and monitoring; trusted proxy configuration.
- A durable email outbox, MFA and independent security review before wider rollout.

## References

- Flask-Login alternative tokens: https://flask-login.readthedocs.io/en/latest/
- Flask-WTF scoped CSRF: https://flask-wtf.readthedocs.io/en/latest/csrf/
- OWASP recovery guidance: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
