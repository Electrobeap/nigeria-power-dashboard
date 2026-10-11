# NigeriaPowerData — Free + Pro Subscription MVP

Status: **implementation specification only; no billing or access control is live**  
Target branch: `feature/free-pro-subscriptions-20261011`  
Product owner: Jirow Technologies Limited  
Draft date: 2026-10-11

## Existing codebase — verified

- Production app is Flask 3 with server-rendered Jinja templates, Bootstrap, vanilla JavaScript, SQLAlchemy, Flask-Migrate, PostgreSQL and Render.
- App factory: `grid_monitor/__init__.py`; API blueprint: `grid_monitor/routes/api.py`; pages: `grid_monitor/routes/web.py`.
- Models: `grid_monitor/models.py`; current navigation: `grid_monitor/templates/partials/nav.html`; main site UI: `grid_monitor/templates/index.html`; chart client: `grid_monitor/static/js/dashboard.js`.
- Current endpoints `/api/history`, `/api/generation`, and `/api/analytics` accept historical windows up to **8760 hours**, while entity endpoints accept up to **720 hours**. Dashboard buttons expose 24h, 7d, 30d, 90d, and 1y windows.
- CSV export currently runs client-side using data already returned from the API. Merely hiding the export button or long-range buttons is **not** authorization.
- Current `grid_monitor/models.py` and `requirements.txt` have no user, subscription or Paystack models/integration. Existing privacy copy currently says accounts are not used.
- `render.yaml` has `autoDeploy: true`; do not commit work directly to `main`.

## Scope and pricing (to be validated by founder)

**Community — Free:** preserve existing live dashboards, current metrics, 24h/7d generation views, publicly intended entity summaries, and public articles. Do not remove an existing public 7d view without explicit product approval. Basic 24h export can remain free if needed for continuity.

**Pro — ₦7,500/month in NGN and proposed $9/month in USD (separate, provisional market prices):** 30d/90d/1y generation and historical analytics (subject to actual data availability), premium full-range CSV export, and authenticated premium access. No guarantee that the database already contains one year of history; show actual available coverage. USD is display/architecture-ready only until settlement capability is separately approved.

**Business and Enterprise:** `Contact Sales` placeholders only; no automated billing or promises of unbuilt features in this MVP.

This phase targets individual Pro accounts only. Multi-seat organizations, commercial API-key billing, scheduled reports and Paystack annual plans are deferred.

## Amendment — dual-currency readiness (2026-10-11; supersedes conflicting single-currency instructions)

**Business decision:** architect subscriptions for **NGN + USD**, but **do not activate live USD checkout**. Founder has a **personal** Zenith USD domiciliary account, not an approved corporate USD settlement account for Jirow Technologies Limited. Do not collect or request personal banking credentials, and do not route company receipts through a personal account.

- **Price proposals, subject to validation:** Community Free in both currencies; Pro **NGN 7,500/month** and **USD 9/month**. Business **NGN 35,000/month** and **USD 39/month** are *future illustrative prices only*; Business/Enterprise remain `Contact Sales` in the Free + Pro MVP. Prices are market-specific, **not real-time FX conversions**.
- Build a `currency` field on subscriptions, payment transactions, invoices, and server-side provider plan mappings from day one; represent amounts in integer **minor units** with ISO 4217 currency codes. Keep pricing records/versioning auditable so rates can change for new subscribers without silently changing contracted recurring amounts.
- Add a transparent **manual NGN/USD selector** on the pricing page. Do not infer payment eligibility exclusively from IP geolocation or the browser locale. Selection is not a billing entitlement.
- In the first implementation, NGN checkout remains behind Paystack sandbox / production feature flags; actual production activation requires approved company onboarding, verified settlement arrangements, consent and manual release. USD shows `Coming soon` or `Contact sales`, with **no active checkout**, until Jirow's corporate USD settlement and provider support have been verified.
- When USD becomes authorized, create **distinct server-side provider plan identifiers** for NGN and USD; verify provider support for recurring USD charges, the company's eligibility, settlement bank requirements, payout costs and supported payment methods before adding live checkout. Do not silently charge international buyers in USD if only NGN is authorized.
- Paystack choice is provisional pending onboarding. Keep a clear billing-provider service boundary so other eligible processors can be considered without rewriting user entitlements. Never expose provider keys or let the browser dictate the charge amount or currency.
- For accounting, store the **original charge currency/amount** (plus provider settlement amounts, fees, refunds and exchange details if applicable); separately calculate normalized USD ARR for internal reporting, using documented exchange rates and conversion dates.
- When implementing PR A, **do not integrate or activate live payments**. Implement a secure schema and pricing UI with disabled USD actions only. PR C should implement NGN test-mode charges first, USD test support only after verified provider capabilities; live USD is a separate future go-live decision.
- Test NGN and USD prices separately, currency tampering (e.g. client sends USD while claiming NGN plan), plan-ID mismatch, duplicate webhook events, and currency-specific entitlement / refund reconciliation. Update the earlier single-currency spec as needed, without rebuilding the site or changing the current public dashboard.

## Priority production blocker — state and regional drill-down timeouts (2026-10-11)

**Do this before merging or activating subscriptions.** In August, `/state/lagos` returned 502 in production even when the homepage worked. All 37 state routes once passed local tests after an optimization, but production verification was incomplete. On 2026-10-11 the public `/states` directory and homepage loaded while external fetches of `/state/lagos`, `/state/edo`, and `/region/north-central` timed out. This is a **reproduction signal, not a confirmed root cause or HTTP status for today's failures**.

Read `grid_monitor/routes/web.py` `_geo_seo_context()`, `state_page()`, `region_page()`, `grid_monitor/services/state_intelligence.py` `_allocation_series()`, `_snapshot_rows()`, `state_intelligence()`, and the state/region JSON routes in `grid_monitor/routes/api.py`.

**Hypothesis to test:** server-side HTML rendering awaits expensive cached-or-uncached historical intelligence and SQLAlchemy snapshot loading; when it stalls, pages never render. Existing start/served/failed request log events can show whether Flask receives and finishes requests. Inspect actual Render logs for `state_page_started` without matching `state_page_served`, `WORKER TIMEOUT`, SIGKILL/OOM, tracebacks, database query timeouts, connection pool saturation, and worker restarts. Compare production `/state/lagos`, `/state/edo`, `/region/north-central` and JSON `/api/states/lagos`/`/api/regions/north-central`; measure response timing and SQL execution time. Verify custom-domain vs Render service URL only if warranted.

**Fix requirements:**
- Avoid any costly historical DB query blocking the initial state/region HTML. Prefer fast metadata generated from existing static `STATE_PROFILES` / `REGION_LABELS`, with async client-side analytics API fetch and transparent loading/error states. Keep accurate SEO descriptions while labelling estimates honestly.
- Optimize API historical queries and SQL loading, fallbacks, caches, query bounds and concurrency; avoid reintroducing N+1, large unbounded joins, or synchronous retries.
- Remain responsive if historical data is missing, stale, slow, or unavailable; do not render fake/placeholder figures as measurements.
- Verify 37/37 states, six regions, representative geo hierarchy drill-downs, and corresponding APIs; unknown slugs must 404 correctly. Test warm/cold cache, realistic production-like PostgreSQL volume, and concurrent access. Include elapsed request timings.
- Do not change production `main` until reviewed and deployed through the normal process. Do not hide errors by increasing Gunicorn timeout alone.
- **Stop/go:** No release of subscriptions/payment gating until the production drill-down routes reliably respond and analytics failures are gracefully handled.

## Development order

### PR A — Readiness and account system (no live charges)
1. Run repository tests, map all public historical routes and any JSON embedded in rendered HTML; identify bypasses. Add a short written report.
2. Build a responsive `/pricing` page, `/register`, `/login`, `/logout`, `/account`, and a clear upgrade flow using the site's current design language. Add a Pricing nav link.
3. Add database models and proper Alembic migrations for users, plan entitlements, and subscriptions. Use server-controlled plan assignment; default new accounts to free.
4. Use established Flask authentication patterns (secure password hashing, CSRF-protected forms, secure signed session cookies, login throttling, password reset/email verification where delivery is configured). Do not expose credentials, tokens or personally identifying data in logs.
5. Set authenticated/account responses to `Cache-Control: private, no-store`, while preserving public caching strategy.
6. Centralize permissions in a server-side entitlement service, rather than checking the displayed pricing plan in JavaScript.
7. Keep `SUBSCRIPTIONS_ENABLED=false` by default. With this setting off, existing public API behavior and dashboard must not regress.
8. Update privacy, terms, and documentation for customer accounts before production signup.
9. Add tests for account creation/login/logout, authentication failures, migrations and current public dashboard behavior.

### PR B — Server-side Pro authorization (feature-flagged)
1. Establish a **single, documented permission matrix** for every endpoint capable of returning historical data: `/api/history`, `/api/generation`, `/api/analytics`, and entity/state/region drill-down endpoints; check other aliases and rendered HTML payloads too.
2. When the feature flag is enabled, allow anonymous/Free requests for the public baseline (up to 168 hours where already public); require active Pro for greater ranges. Return a consistent `403` JSON error with code `subscription_required` and an upgrade URL; do not silently truncate premium queries or return premium data.
3. Protect CSV datasets with the same authorization as their underlying queries. Limit the free 24h/7d export as product-approved; premium data must not be downloadable from a direct endpoint or alternate route.
4. Adapt 30d/90d/1y dashboard range buttons to display a login/upgrade action when unauthorised. Do not break 24h or 7d charts and other public widgets.
5. Test anonymous/Free/Pro/expired subscription access, API aliases, out-of-range inputs, cached responses and protection against bypass through alternate endpoints.
6. Preserve collection scheduler, scraping, data persistence, article pages, SEO, and the current health endpoint.

### PR C — Paystack **test mode** billing (no live charges)
1. Add payment initiation for Pro monthly subscription using the **server-side configured** Paystack plan code. Never accept an arbitrary amount, currency or plan code from a browser request.
2. Use Paystack test credentials supplied through environment variables. Never hardcode secrets, expose secret keys to browsers, or commit an `.env` file.
3. Verify each transaction server-side with Paystack and authenticate webhook payloads via Paystack's documented HMAC-SHA512 signature process. Make webhook processing **idempotent**, with unique provider event/payment references.
4. Activate or renew Pro only after independently verified successful payment events. Model pending, active, overdue, cancelled and expired states with explicit expiry and payment reconciliation.
5. Implement account billing status, renewal/cancel paths and clear customer-facing errors; preserve Pro until the paid-through date when appropriate.
6. Do not enable Paystack live mode, public signup or gating in production until product owner signs off on tests, data rights and operational readiness.
7. Provide manual sandbox test instructions: success, declined charge, repeated webhook, forged webhook, missing callback, delayed event, cancellation, renewal, expired plan and refund/dispute.

## Deployment guardrails

- Work only on a feature branch and open a reviewable pull request. Never merge automatically or enable live charges.
- Paystack secret must remain server-only. All user input and webhooks require validation.
- Set a strong production `SECRET_KEY` securely via hosting environment. Ensure robust session cookie defaults for HTTPS.
- Do not use robots.txt, CSS or client JavaScript as access control.
- Check contractual/redistribution rights for NISO/NIGGRID data and distinguish real measurements from planning-grade estimates before monetizing datasets.
- Existing `/<page_slug>` content route must not swallow new named auth/pricing routes.
- Ensure migrations do not drop historical grid data, and consider existing startup migration behavior.
- Update sitemap to include public `/pricing`, while excluding auth/account/payment URLs.
- Document environment variables, setup, rollback and monitoring.

## Acceptance criteria

- Site remains functional with feature flags off and no Paystack configuration.
- Existing public pages and 24h/7d charts remain available when gating is enabled.
- Direct HTTP API requests cannot access >7d historical data without an active Pro entitlement.
- Authenticated users can inspect their plan and never access another user's billing information.
- No live payment processing is possible before explicit go-live configuration and review.
- Tests cover entitlement expiry, forged/repeated webhooks, pagination and multiple possible data routes.
- Final PR includes a changed-files summary, migration notes, test commands/results, rollout steps and remaining risks.
