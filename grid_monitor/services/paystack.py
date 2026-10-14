"""Small, fixed-origin Paystack adapter. Only test keys and reviewed NGN plans."""
import re
from urllib.parse import urlsplit

from flask import current_app
import requests

from grid_monitor.services.subscriptions import PRO_AMOUNTS_MINOR

API_ORIGIN = "https://api.paystack.co"
PRODUCTION_HOSTS = {"nigeriapowerdata.com", "www.nigeriapowerdata.com",
                    "nigeria-power-dashboard-1.onrender.com"}


class BillingError(Exception):
    def __init__(self, code="provider_unavailable", retryable=True):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def sandbox_enabled():
    return bool(current_app.config.get("PAYSTACK_TEST_CHECKOUT_ENABLED"))


def validate_sandbox_config(app):
    config = app.config
    if config.get("LIVE_BILLING_ENABLED") or config.get("USD_CHECKOUT_ENABLED"):
        raise RuntimeError("Live and USD billing are blocked in this release.")
    if not config.get("PAYSTACK_TEST_CHECKOUT_ENABLED"):
        return
    if not (config.get("ACCOUNTS_ENABLED") and config.get("SUBSCRIPTIONS_ENABLED")):
        raise RuntimeError("Sandbox billing requires enabled accounts and subscriptions.")
    origin = str(config.get("PAYSTACK_SANDBOX_ORIGIN", "")).rstrip("/")
    parsed = urlsplit(origin)
    if (config.get("BILLING_ENVIRONMENT") != "staging" or not origin
            or origin != str(config.get("APP_BASE_URL", "")).rstrip("/")
            or parsed.scheme != "https" or not parsed.hostname
            or parsed.hostname in PRODUCTION_HOSTS
            or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise RuntimeError("Sandbox billing requires an explicitly approved non-production HTTPS staging origin.")
    if not re.fullmatch(r"sk_test_[A-Za-z0-9]{16,128}", config.get("PAYSTACK_SECRET_KEY", "")):
        raise RuntimeError("Sandbox billing requires a Paystack test secret key.")
    if not re.fullmatch(r"PLN_[A-Za-z0-9]{3,80}", config.get("PAYSTACK_NGN_PRO_PLAN_CODE", "")):
        raise RuntimeError("Configure an actual Paystack NGN test plan.")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", str(config.get("PAYSTACK_TEST_INTEGRATION_ID", ""))):
        raise RuntimeError("Configure the Paystack test integration ID.")


def identifier(value, prefix=None):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.=-]{1,100}", value):
        raise BillingError("invalid_provider_identifier", False)
    if prefix and not value.startswith(prefix):
        raise BillingError("invalid_provider_identifier", False)
    return value


def provider_url(value, kind):
    parsed = urlsplit(str(value))
    host = "checkout.paystack.com" if kind == "checkout" else "paystack.com"
    prefix = "/" if kind == "checkout" else "/manage/subscriptions/"
    if (parsed.scheme != "https" or parsed.hostname != host or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment
            or not parsed.path.startswith(prefix) or len(value) > 512):
        raise BillingError("invalid_provider_redirect", False)
    return value


def test_object(data):
    if not isinstance(data, dict) or data.get("domain") != "test":
        raise BillingError("non_test_provider_object", False)
    integration = data.get("integration")
    if isinstance(integration, dict):
        integration = integration.get("id")
    if str(integration) != str(current_app.config["PAYSTACK_TEST_INTEGRATION_ID"]):
        raise BillingError("wrong_integration", False)
    return data


def validate_plan(data, expected=None):
    test_object(data)
    if (data.get("plan_code") != (expected or current_app.config["PAYSTACK_NGN_PRO_PLAN_CODE"])
            or data.get("currency") != "NGN"
            or type(data.get("amount")) is not int or data["amount"] != PRO_AMOUNTS_MINOR["NGN"]
            or data.get("interval") != "monthly"):
        raise BillingError("plan_configuration_mismatch", False)
    return data


class Paystack:
    def request(self, method, path, *, payload=None, params=None):
        if not sandbox_enabled():
            raise BillingError("billing_disabled", False)
        validate_sandbox_config(current_app)
        try:
            # Never follow redirects or inherit an arbitrary proxy carrying the key.
            with requests.Session() as session:
                session.trust_env = False
                with session.request(method, API_ORIGIN + path, json=payload, params=params,
                        headers={"Authorization": "Bearer " + current_app.config["PAYSTACK_SECRET_KEY"],
                                 "Accept": "application/json"}, timeout=(3, 8),
                        allow_redirects=False, stream=True) as response:
                    if response.status_code != 200:
                        raise BillingError("provider_unavailable", response.status_code >= 500 or response.status_code == 429)
                    raw = bytearray()
                    for chunk in response.iter_content(16384):
                        raw.extend(chunk)
                        if len(raw) > 1048576:
                            raise BillingError("provider_response_too_large", False)
                    import json
                    body = json.loads(raw)
            if not isinstance(body, dict) or body.get("status") is not True or "data" not in body:
                raise BillingError("provider_response_invalid")
            return body["data"]
        except (requests.RequestException, ValueError, TypeError):
            # Provider bodies, request headers and exception strings may contain secrets.
            raise BillingError("provider_unavailable") from None

    def plan(self):
        code = identifier(current_app.config["PAYSTACK_NGN_PRO_PLAN_CODE"], "PLN_")
        return validate_plan(self.request("GET", "/plan/" + code))

    def initialize(self, email, reference, plan):
        return self.request("POST", "/transaction/initialize", payload={
            "email": email, "reference": reference, "plan": plan,
            "amount": PRO_AMOUNTS_MINOR["NGN"], "currency": "NGN", "channels": ["card"],
            "callback_url": current_app.config["PAYSTACK_SANDBOX_ORIGIN"].rstrip("/") + "/billing/paystack/callback",
        })

    def verify(self, reference):
        return self.request("GET", "/transaction/verify/" + identifier(reference))

    def subscription(self, code):
        return self.request("GET", "/subscription/" + identifier(code, "SUB_"))

    def subscriptions(self, customer_id, plan_id):
        result = self.request("GET", "/subscription", params={
            "customer": int(customer_id), "plan": int(plan_id), "perPage": 100, "page": 1})
        if not isinstance(result, list) or len(result) >= 100:
            raise BillingError("subscription_match_requires_review", False)
        return result

    def cancel(self, code, token):
        return self.request("POST", "/subscription/disable", payload={"code": identifier(code, "SUB_"), "token": token})

    def manage(self, code):
        data = self.request("GET", "/subscription/" + identifier(code, "SUB_") + "/manage/link")
        return provider_url(data.get("link"), "manage")


def provider():
    return Paystack()
