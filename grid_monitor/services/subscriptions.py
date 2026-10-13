"""Independent introductory prices, adapted from the original subscription branch."""
from dataclasses import asdict, dataclass

from flask import current_app
from sqlalchemy.exc import IntegrityError

from grid_monitor.extensions import db
from grid_monitor.subscription_models import SubscriptionPlanPrice

SUPPORTED_CURRENCIES = ("NGN", "USD")
PRICING_VERSION = 1
PRO_AMOUNTS_MINOR = {"NGN": 750000, "USD": 900}


@dataclass(frozen=True)
class PlanPriceConfig:
    plan_code: str
    display_name: str
    currency: str
    amount_minor: int | None
    formatted_price: str
    description: str
    features: tuple[str, ...]
    interval: str | None = "month"
    checkout_enabled: bool = False


def normalize_currency(value=None):
    currency = str(value or "NGN").strip().upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError("Choose NGN or USD.")
    return currency


def plan_catalog(currency=None):
    currency = normalize_currency(currency)
    return [
        PlanPriceConfig("community", "Community", currency, 0, "Free",
                        "Public electricity intelligence.",
                        ("National, regional and state dashboards", "Existing public historical views",
                         "Educational articles and eligible research papers")),
        PlanPriceConfig("pro", "Pro", currency, PRO_AMOUNTS_MINOR[currency],
                        "\u20a67,500" if currency == "NGN" else "$9",
                        "Provisional introductory monthly price. Checkout is not available.",
                        ("Extended history, subject to available coverage", "Advanced exports, pending release",
                         "Town/city intelligence: currently free under Pro Preview")),
        PlanPriceConfig("business", "Business", currency, None, "Contact Sales",
                        "Discuss commercial analytics requirements.", ("Team and commercial services by agreement",),
                        interval=None),
        PlanPriceConfig("enterprise", "Enterprise", currency, None, "Contact Sales",
                        "Discuss enterprise and research requirements.", ("Custom scope and data-rights review",),
                        interval=None),
    ]


def pricing_payload(currency=None):
    currency = normalize_currency(currency)
    return {"currency": currency, "currencies": list(SUPPORTED_CURRENCIES),
            "version": PRICING_VERSION, "provisional": True, "billing_enabled": False,
            "usd_checkout_enabled": False, "plans": [asdict(plan) for plan in plan_catalog(currency)]}


def seed_subscription_pricing():
    """Explicit CLI only. Never rewrite a contracted version or seed at startup."""
    for currency in SUPPORTED_CURRENCIES:
        for plan in plan_catalog(currency)[:2]:
            row = SubscriptionPlanPrice.query.filter_by(
                plan_code=plan.plan_code, currency=currency, version=PRICING_VERSION,
            ).one_or_none()
            if row:
                if row.amount_minor != plan.amount_minor or row.interval != "month":
                    db.session.rollback()
                    raise ValueError("Existing price version differs; create a reviewed new version.")
            else:
                db.session.add(SubscriptionPlanPrice(plan_code=plan.plan_code, currency=currency,
                                                    version=PRICING_VERSION, amount_minor=plan.amount_minor))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError("Pricing was changed concurrently; rerun the reviewed seed command.") from None
