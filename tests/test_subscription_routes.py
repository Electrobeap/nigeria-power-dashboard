import pytest

from grid_monitor.services.billing_providers import BillingProviderError, CheckoutRequest, PaystackTestModeProvider
from grid_monitor.services.subscriptions import pricing_payload


def test_pricing_page_renders_currency_selector(client):
    response = client.get("/pricing?currency=USD")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Pricing built for Nigerian and international energy analysts" in html
    assert "$9" in html
    assert "USD checkout stays disabled" in html
    assert "₦7,500" not in html


def test_pricing_api_returns_response_timestamp(client):
    response = client.get("/api/subscriptions/pricing?currency=NGN")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["currency"] == "NGN"
    assert payload["response_timestamp"]
    pro = next(plan for plan in payload["plans"] if plan["plan_code"] == "pro")
    assert pro["amount_minor"] == 750000
    assert pro["checkout_enabled"] is False


def test_paystack_initialize_is_disabled_when_subscriptions_flag_off(client):
    response = client.post(
        "/api/billing/paystack/initialize",
        json={"email": "analyst@example.com", "plan_code": "pro", "currency": "NGN"},
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "subscriptions_disabled"


def test_paystack_provider_blocks_live_keys(app_context):
    app_context.config["SUBSCRIPTIONS_ENABLED"] = True
    app_context.config["PAYSTACK_TEST_MODE"] = True
    app_context.config["PAYSTACK_TEST_CHECKOUT_ENABLED"] = True
    app_context.config["PAYSTACK_SECRET_KEY"] = "sk_live_not_allowed"
    provider = PaystackTestModeProvider()
    with pytest.raises(BillingProviderError):
        provider.initialize_checkout(
            CheckoutRequest(email="analyst@example.com", plan_code="pro", currency="NGN")
        )


def test_usd_pricing_never_enables_checkout(app_context):
    app_context.config["SUBSCRIPTIONS_ENABLED"] = True
    app_context.config["PAYSTACK_TEST_CHECKOUT_ENABLED"] = True
    app_context.config["PAYSTACK_SECRET_KEY"] = "sk_test_example"
    pro = next(plan for plan in pricing_payload("USD")["plans"] if plan["plan_code"] == "pro")
    assert pro["checkout_enabled"] is False
    assert pro["cta_mode"] == "coming-soon"
