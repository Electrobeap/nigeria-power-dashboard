# Subscription Readiness Implementation

Status: feature branch implementation only. Do not merge to production or enable live billing until the open requirements below are complete.

## What This Adds

- Dual-currency subscription architecture for NGN and USD.
- Server-side price catalog with separate currency-specific prices, not FX conversion.
- Public `/pricing` page with a manual NGN/USD selector.
- Pricing API at `/api/subscriptions/pricing`.
- Entitlement snapshot API at `/api/subscriptions/entitlements`.
- Additive database schema for users, plan prices, provider plan mappings, subscriptions, transactions, invoices, and webhook events.
- Paystack provider boundary prepared for NGN sandbox checkout only.
- USD checkout disabled until Jirow Technologies Limited has approved corporate USD settlement and provider eligibility.
- No dashboard gating, no premium restrictions, and no live payment collection by default.

## Current Introductory Price Catalog

| Plan | NGN | USD | Status |
| --- | ---: | ---: | --- |
| Community | Free | Free | Public access |
| Pro | NGN 7,500/month | USD 9/month | NGN sandbox-ready, USD coming soon |
| Business | NGN 35,000/month | USD 39/month | Future release / contact sales |
| Enterprise | Custom | Custom | Contact sales |

Prices are market-specific configuration values and must not be treated as automatic exchange-rate conversions.

## Database Tables

The migration `c7d8e9f0a123_add_subscription_readiness_schema.py` creates:

- `users`
- `subscription_plan_prices`
- `payment_provider_plans`
- `user_subscriptions`
- `payment_transactions`
- `billing_invoices`
- `payment_webhook_events`

Subscription and payment rows store ISO currency codes and integer minor-unit amounts. Provider references are stored server-side for reconciliation and future webhook idempotency. Secrets are never stored in these tables.

## Environment Variables

| Variable | Default | Notes |
| --- | --- | --- |
| `SUBSCRIPTIONS_ENABLED` | `0` | Master flag. Keep off until auth, entitlement, and go-live testing pass. |
| `SUBSCRIPTION_SEED_PRICING_ENABLED` | `1` | Seeds auditable server-side plan prices after startup migrations/table creation. |
| `BILLING_PROVIDER` | `paystack` | Provider boundary placeholder. |
| `PAYSTACK_TEST_MODE` | `1` | Required for sandbox checkout. |
| `PAYSTACK_TEST_CHECKOUT_ENABLED` | `0` | Explicit sandbox checkout activation flag. |
| `PAYSTACK_PUBLIC_KEY` | unset | Public test key for future UI checkout work. |
| `PAYSTACK_SECRET_KEY` | unset | Server-only secret. Sandbox checkout requires an `sk_test_` value. |
| `PAYSTACK_PRO_NGN_PLAN_CODE` | unset | Server-side Paystack test plan code for NGN Pro. |
| `PAYSTACK_BASE_URL` | `https://api.paystack.co` | Paystack API base URL. |
| `PAYSTACK_TIMEOUT_SECONDS` | `12` | Provider request timeout. |
| `USD_CHECKOUT_ENABLED` | `0` | Must remain off until corporate USD settlement is approved. |
| `USD_PRO_PROVIDER_PLAN_CODE` | unset | Reserved for a future approved USD provider plan. |

## Safety Rules

- Do not use the founder's personal domiciliary account for company settlement.
- Do not enable live Paystack keys in this branch.
- Do not let browsers send charge amounts, currencies, or provider plan IDs as authority.
- Do not activate dashboard restrictions before authentication and entitlement flows are fully tested.
- Keep the public dashboard, data collection, historical records, articles, SEO, and APIs available while `SUBSCRIPTIONS_ENABLED=0`.

## Test Coverage Added

- Currency normalization defaults to NGN and supports USD explicitly.
- Pro prices are distinct for NGN and USD.
- USD checkout is disabled with corporate settlement messaging.
- Business stays contact-sales in both currencies.
- Pricing page renders the selected currency.
- Pricing API returns timestamped JSON.
- Paystack checkout endpoint stays disabled while the master flag is off.
- Paystack provider rejects live keys even if sandbox checkout flags are enabled.

## Outstanding Requirements Before Go-Live

- Build register/login/logout/account flows with CSRF protection, throttling, password reset, and email verification where delivery is configured.
- Add server-side entitlement gates for premium historical windows and CSV exports behind `SUBSCRIPTIONS_ENABLED`.
- Implement webhook persistence and idempotent transaction/subscription activation.
- Add Paystack sandbox test fixtures for success, declined, duplicate webhook, forged signature, delayed callback, cancellation, renewal, expiry, and refunds/disputes.
- Complete legal, data-rights, tax, accounting, refund, and settlement review.
- Confirm Jirow Technologies Limited corporate settlement accounts and provider eligibility before live billing.
- Resolve and verify state/regional drill-down production timeout risks before any subscription rollout.
