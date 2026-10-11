from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import requests
from flask import current_app

from grid_monitor.services.subscriptions import get_plan, normalize_currency, provider_plan_code


class BillingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckoutRequest:
    email: str
    plan_code: str
    currency: str
    callback_url: str | None = None
    metadata: dict[str, Any] | None = None


class PaystackTestModeProvider:
    """Small Paystack boundary for NGN sandbox checkout only.

    Live payment collection remains blocked by configuration and key validation.
    The browser never supplies amount, currency, or provider plan code directly.
    """

    provider = "paystack"

    def __init__(self) -> None:
        self.base_url = current_app.config.get("PAYSTACK_BASE_URL", "https://api.paystack.co").rstrip("/")
        self.secret_key = current_app.config.get("PAYSTACK_SECRET_KEY", "")
        self.test_mode = bool(current_app.config.get("PAYSTACK_TEST_MODE"))
        self.checkout_enabled = bool(current_app.config.get("PAYSTACK_TEST_CHECKOUT_ENABLED"))

    def assert_test_mode(self) -> None:
        if not self.test_mode or not self.checkout_enabled:
            raise BillingProviderError("Paystack checkout is disabled. Enable test-mode flags explicitly for sandbox testing.")
        if not self.secret_key.startswith("sk_test_"):
            raise BillingProviderError("Paystack test checkout requires a server-side sk_test_ key.")

    def initialize_checkout(self, request: CheckoutRequest) -> dict[str, Any]:
        self.assert_test_mode()
        currency = normalize_currency(request.currency)
        plan = get_plan(request.plan_code, currency)
        if not plan or not plan.checkout_enabled:
            raise BillingProviderError("Selected plan is not available for checkout.")
        if currency != "NGN":
            raise BillingProviderError("USD checkout is disabled until corporate USD settlement is approved.")
        provider_plan = provider_plan_code(request.plan_code, currency)
        if not provider_plan:
            raise BillingProviderError("Paystack NGN provider plan code is not configured.")

        payload = {
            "email": request.email,
            "amount": plan.amount_minor,
            "currency": currency,
            "plan": provider_plan,
            "metadata": {
                "plan_code": plan.plan_code,
                "currency": currency,
                "amount_minor": plan.amount_minor,
                "source": "nigeria_power_data_subscription_test",
                **(request.metadata or {}),
            },
        }
        if request.callback_url:
            payload["callback_url"] = request.callback_url

        response = requests.post(
            f"{self.base_url}/transaction/initialize",
            json=payload,
            headers={"Authorization": f"Bearer {self.secret_key}"},
            timeout=current_app.config.get("PAYSTACK_TIMEOUT_SECONDS", 12),
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("status"):
            raise BillingProviderError(data.get("message") or "Paystack checkout initialization failed.")
        return data

    def verify_transaction(self, reference: str) -> dict[str, Any]:
        self.assert_test_mode()
        response = requests.get(
            f"{self.base_url}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {self.secret_key}"},
            timeout=current_app.config.get("PAYSTACK_TIMEOUT_SECONDS", 12),
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("status"):
            raise BillingProviderError(data.get("message") or "Paystack transaction verification failed.")
        return data

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature or not self.secret_key:
            return False
        expected = hmac.new(self.secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)
