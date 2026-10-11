from grid_monitor.services.subscriptions import get_plan, normalize_currency, pricing_payload


def test_currency_normalization_defaults_to_ngn(app_context):
    assert normalize_currency(None) == "NGN"
    assert normalize_currency("usd") == "USD"
    assert normalize_currency("eur") == "NGN"


def test_pro_prices_are_currency_specific(app_context):
    ngn = get_plan("pro", "NGN")
    usd = get_plan("pro", "USD")
    assert ngn.amount_minor == 750000
    assert ngn.formatted_price == "₦7,500"
    assert usd.amount_minor == 900
    assert usd.formatted_price == "$9"
    assert ngn.amount_minor != usd.amount_minor


def test_usd_checkout_is_disabled(app_context):
    payload = pricing_payload("USD")
    pro = next(plan for plan in payload["plans"] if plan["plan_code"] == "pro")
    assert pro["checkout_enabled"] is False
    assert pro["cta_mode"] == "coming-soon"
    assert "corporate USD settlement" in pro["footnote"]


def test_business_is_contact_sales_in_both_currencies(app_context):
    for currency in ("NGN", "USD"):
        business = next(plan for plan in pricing_payload(currency)["plans"] if plan["plan_code"] == "business")
        assert business["cta_mode"] == "contact-sales"
        assert business["checkout_enabled"] is False
