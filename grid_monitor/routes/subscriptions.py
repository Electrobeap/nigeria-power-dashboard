from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from grid_monitor.services.billing_providers import BillingProviderError, CheckoutRequest, PaystackTestModeProvider
from grid_monitor.services.entitlements import entitlement_snapshot
from grid_monitor.services.social_meta import build_social_meta
from grid_monitor.services.structured_data import build_structured_data
from grid_monitor.services.subscriptions import available_currencies, normalize_currency, pricing_payload
from grid_monitor.utils.time import utc_now_iso


subscription_bp = Blueprint("subscriptions", __name__)


def _timestamped(payload: dict, status: int = 200):
    payload = dict(payload)
    payload.setdefault("response_timestamp", utc_now_iso())
    return payload, status


def _pricing_schema(title: str, description: str, path: str):
    breadcrumbs = [{"name": "Home", "path": "/"}, {"name": "Pricing", "path": path}]
    return build_structured_data(
        title=title,
        description=description,
        path=path,
        breadcrumbs=breadcrumbs,
        page_type="WebPage",
        article_type="Article",
        article_sections=["Community", "Pro", "Business", "Enterprise"],
        faq_items=[
            {
                "question": "Is subscription billing live?",
                "answer": "No. Nigeria Power Data subscription billing is implementation-ready but disabled by default. Paystack checkout is prepared only for NGN sandbox testing.",
            },
            {
                "question": "Can customers pay in USD today?",
                "answer": "No. USD checkout remains disabled until Jirow Technologies Limited has approved corporate USD settlement and payment-provider eligibility.",
            },
            {
                "question": "Will public dashboards remain accessible?",
                "answer": "Yes. Existing dashboards, articles, public data pages, and current public APIs remain available while entitlement controls are tested.",
            },
        ],
    )


@subscription_bp.get("/pricing")
def pricing_page():
    currency = normalize_currency(request.args.get("currency"))
    title = "Nigeria Power Data Pricing"
    description = (
        "Community access stays free while Pro subscription readiness is prepared with separate NGN and USD pricing. "
        "Live billing and premium restrictions remain disabled until final review."
    )
    return render_template(
        "pricing.html",
        title=title,
        description=description,
        canonical_path="/pricing",
        pricing=pricing_payload(currency),
        currencies=available_currencies(),
        currency=currency,
        social_meta=build_social_meta(title, description, "/pricing"),
        structured_data=_pricing_schema(title, description, "/pricing"),
    )


@subscription_bp.get("/api/subscriptions/pricing")
def pricing_api():
    return _timestamped(pricing_payload(request.args.get("currency")))


@subscription_bp.get("/api/subscriptions/entitlements")
def entitlements_api():
    return _timestamped(entitlement_snapshot())


@subscription_bp.post("/api/billing/paystack/initialize")
def initialize_paystack_checkout():
    if not current_app.config.get("SUBSCRIPTIONS_ENABLED"):
        return _timestamped(
            {
                "error": "Subscriptions are disabled. Existing public access remains unchanged.",
                "code": "subscriptions_disabled",
            },
            403,
        )

    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().lower()
    plan_code = str(payload.get("plan_code") or "pro").strip().lower()
    currency = normalize_currency(payload.get("currency"))
    callback_url = payload.get("callback_url")

    if not email or "@" not in email:
        return _timestamped({"error": "A valid email address is required.", "code": "validation_error"}, 400)
    if plan_code != "pro":
        return _timestamped({"error": "Only the Pro monthly sandbox checkout is prepared.", "code": "plan_not_supported"}, 400)
    if currency == "USD":
        return _timestamped(
            {
                "error": "USD checkout is coming soon and requires approved corporate USD settlement before activation.",
                "code": "usd_checkout_disabled",
            },
            403,
        )

    try:
        provider = PaystackTestModeProvider()
        checkout = provider.initialize_checkout(
            CheckoutRequest(
                email=email,
                plan_code=plan_code,
                currency=currency,
                callback_url=callback_url,
                metadata={"feature_flag": "subscriptions_test_mode"},
            )
        )
    except BillingProviderError as exc:
        return _timestamped({"error": str(exc), "code": "checkout_disabled"}, 403)
    except Exception:
        current_app.logger.exception({"event": "paystack_checkout_initialization_failed"})
        return _timestamped({"error": "Unable to initialize Paystack test checkout.", "code": "provider_error"}, 502)

    return _timestamped({"provider": "paystack", "mode": "test", "checkout": checkout.get("data", {})})
