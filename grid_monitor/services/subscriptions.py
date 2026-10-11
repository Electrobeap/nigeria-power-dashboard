from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from grid_monitor.extensions import db
from grid_monitor.models import PaymentProviderPlan, SubscriptionPlanPrice
from grid_monitor.utils.logging import log_event


SUPPORTED_CURRENCIES = ("NGN", "USD")
SUPPORTED_INTERVALS = ("month",)
PROVIDER_PAYSTACK = "paystack"
PRICING_VERSION = 1


@dataclass(frozen=True)
class PlanPriceConfig:
    plan_code: str
    display_name: str
    tier: str
    currency: str
    amount_minor: int | None
    interval: str | None
    description: str
    features: tuple[str, ...]
    cta_label: str
    cta_mode: str
    checkout_enabled: bool = False
    badge: str | None = None
    footnote: str | None = None

    @property
    def is_paid(self) -> bool:
        return bool(self.amount_minor and self.amount_minor > 0)

    @property
    def amount_major(self) -> float | None:
        if self.amount_minor is None:
            return None
        return self.amount_minor / 100

    @property
    def formatted_price(self) -> str:
        if self.amount_minor is None:
            return "Custom"
        if self.amount_minor == 0:
            return "Free"
        symbol = "₦" if self.currency == "NGN" else "$"
        amount = self.amount_minor / 100
        return f"{symbol}{amount:,.0f}" if amount.is_integer() else f"{symbol}{amount:,.2f}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_currency(value: str | None) -> str:
    currency = (value or "NGN").strip().upper()
    return currency if currency in SUPPORTED_CURRENCIES else "NGN"


def _features(*items: str) -> tuple[str, ...]:
    return tuple(items)


def _ngn_checkout_enabled(plan_code: str) -> bool:
    if plan_code != "pro":
        return False
    return bool(
        current_app.config.get("SUBSCRIPTIONS_ENABLED")
        and current_app.config.get("PAYSTACK_TEST_MODE")
        and current_app.config.get("PAYSTACK_TEST_CHECKOUT_ENABLED")
        and current_app.config.get("PAYSTACK_SECRET_KEY", "").startswith("sk_test_")
        and current_app.config.get("PAYSTACK_PRO_NGN_PLAN_CODE")
    )


def plan_catalog(currency: str | None = None) -> list[PlanPriceConfig]:
    currency = normalize_currency(currency)
    pro_checkout = currency == "NGN" and _ngn_checkout_enabled("pro")
    usd_note = (
        "USD checkout is coming soon. Jirow Technologies Limited must have an approved corporate USD settlement arrangement "
        "and provider confirmation before USD billing is enabled."
    )
    business_note = "Business automation is a future release; contact sales for pilots and research partnerships."
    return [
        PlanPriceConfig(
            plan_code="community",
            display_name="Community",
            tier="Free",
            currency=currency,
            amount_minor=0,
            interval="month",
            description="Public live dashboard access for Nigeria's core grid signals.",
            features=_features(
                "Live generation dashboard",
                "24h and 7d public trends",
                "Public DisCo, GenCo, state, and article pages",
                "Basic export continuity where already public",
            ),
            cta_label="Current public access",
            cta_mode="public",
            badge="Always free",
        ),
        PlanPriceConfig(
            plan_code="pro",
            display_name="Pro",
            tier="Individual Pro",
            currency=currency,
            amount_minor=750000 if currency == "NGN" else 900,
            interval="month",
            description="Premium historical analytics for analysts, researchers, operators, and energy-market teams.",
            features=_features(
                "30d, 90d, and 1y historical analytics when data is available",
                "Full-range CSV export after entitlement controls are tested",
                "Authenticated premium account readiness",
                "Server-side entitlement model; no JavaScript-only gating",
            ),
            cta_label="Paystack test checkout" if pro_checkout else ("Coming soon" if currency == "USD" else "Join Pro waitlist"),
            cta_mode="checkout" if pro_checkout else ("coming-soon" if currency == "USD" else "waitlist"),
            checkout_enabled=pro_checkout,
            badge="Intro price",
            footnote=None if currency == "NGN" else usd_note,
        ),
        PlanPriceConfig(
            plan_code="business",
            display_name="Business",
            tier="Future release",
            currency=currency,
            amount_minor=3500000 if currency == "NGN" else 3900,
            interval="month",
            description="Team workflows, scheduled reports, and organization-level access controls planned for a later release.",
            features=_features(
                "Future multi-seat organization workspace",
                "Future scheduled reports and team access",
                "Commercial API-key billing deferred",
                "Pilot discussions available with Jirow Technologies Limited",
            ),
            cta_label="Contact sales",
            cta_mode="contact-sales",
            checkout_enabled=False,
            badge="Future",
            footnote=business_note if currency == "NGN" else f"{business_note} {usd_note}",
        ),
        PlanPriceConfig(
            plan_code="enterprise",
            display_name="Enterprise",
            tier="Custom",
            currency=currency,
            amount_minor=None,
            interval=None,
            description="Custom research, data, and enterprise intelligence engagements.",
            features=_features(
                "Custom data rights and redistribution review",
                "Custom reporting and advisory workflow",
                "Security, procurement, and legal review support",
                "Dedicated implementation discussions",
            ),
            cta_label="Contact sales",
            cta_mode="contact-sales",
            checkout_enabled=False,
            badge="Custom",
        ),
    ]


def available_currencies() -> tuple[str, ...]:
    return SUPPORTED_CURRENCIES


def get_plan(plan_code: str, currency: str | None = None) -> PlanPriceConfig | None:
    normalized = normalize_currency(currency)
    for plan in plan_catalog(normalized):
        if plan.plan_code == plan_code:
            return plan
    return None


def provider_plan_code(plan_code: str, currency: str) -> str | None:
    currency = normalize_currency(currency)
    if plan_code == "pro" and currency == "NGN":
        return current_app.config.get("PAYSTACK_PRO_NGN_PLAN_CODE")
    if plan_code == "pro" and currency == "USD":
        return current_app.config.get("USD_PRO_PROVIDER_PLAN_CODE")
    return None


def iter_seed_prices() -> Iterable[PlanPriceConfig]:
    for currency in SUPPORTED_CURRENCIES:
        yield from plan_catalog(currency)


def seed_subscription_pricing() -> None:
    """Idempotently stores server-side price records for auditability.

    Prices are intentionally configured per currency and never derived from an
    exchange-rate conversion. The app can render without these rows, but keeping
    them in the database gives future subscriptions stable, auditable price
    versions.
    """
    if not current_app.config.get("SUBSCRIPTION_SEED_PRICING_ENABLED", True):
        return

    try:
        for plan in iter_seed_prices():
            existing = SubscriptionPlanPrice.query.filter_by(
                plan_code=plan.plan_code,
                currency=plan.currency,
                version=PRICING_VERSION,
            ).one_or_none()
            if existing is None:
                existing = SubscriptionPlanPrice(
                    plan_code=plan.plan_code,
                    currency=plan.currency,
                    version=PRICING_VERSION,
                    effective_from=utc_now(),
                )
                db.session.add(existing)
            existing.display_name = plan.display_name
            existing.amount_minor = plan.amount_minor
            existing.interval = plan.interval
            existing.is_active = True
            existing.checkout_enabled = plan.checkout_enabled
            existing.provider = PROVIDER_PAYSTACK if plan.currency == "NGN" and plan.plan_code == "pro" else None
            existing.metadata_json = {
                "tier": plan.tier,
                "description": plan.description,
                "features": list(plan.features),
                "cta_mode": plan.cta_mode,
                "test_mode_only": plan.plan_code == "pro" and plan.currency == "NGN",
                "usd_checkout_disabled": plan.currency == "USD",
            }

            code = provider_plan_code(plan.plan_code, plan.currency)
            if code:
                mapping = PaymentProviderPlan.query.filter_by(
                    provider=PROVIDER_PAYSTACK,
                    plan_code=plan.plan_code,
                    currency=plan.currency,
                    environment="test" if current_app.config.get("PAYSTACK_TEST_MODE") else "disabled",
                ).one_or_none()
                if mapping is None:
                    mapping = PaymentProviderPlan(
                        provider=PROVIDER_PAYSTACK,
                        plan_code=plan.plan_code,
                        currency=plan.currency,
                        environment="test" if current_app.config.get("PAYSTACK_TEST_MODE") else "disabled",
                    )
                    db.session.add(mapping)
                mapping.provider_plan_code = code
                mapping.amount_minor = plan.amount_minor
                mapping.interval = plan.interval
                mapping.is_active = bool(plan.checkout_enabled)
        db.session.commit()
        log_event("subscription_pricing_seeded")
    except SQLAlchemyError as exc:
        db.session.rollback()
        log_event("subscription_pricing_seed_failed", level=logging.WARNING, error=str(exc))


def pricing_payload(currency: str | None = None) -> dict:
    currency = normalize_currency(currency)
    return {
        "currency": currency,
        "currencies": list(SUPPORTED_CURRENCIES),
        "subscriptions_enabled": bool(current_app.config.get("SUBSCRIPTIONS_ENABLED")),
        "paystack_test_mode": bool(current_app.config.get("PAYSTACK_TEST_MODE")),
        "usd_checkout_enabled": bool(current_app.config.get("USD_CHECKOUT_ENABLED")),
        "plans": [
            {
                "plan_code": plan.plan_code,
                "display_name": plan.display_name,
                "tier": plan.tier,
                "currency": plan.currency,
                "amount_minor": plan.amount_minor,
                "formatted_price": plan.formatted_price,
                "interval": plan.interval,
                "description": plan.description,
                "features": list(plan.features),
                "cta_label": plan.cta_label,
                "cta_mode": plan.cta_mode,
                "checkout_enabled": plan.checkout_enabled,
                "badge": plan.badge,
                "footnote": plan.footnote,
            }
            for plan in plan_catalog(currency)
        ],
    }
