"""In-process HTTP fixtures for the real Paystack adapter. No network or runtime switch."""
from __future__ import annotations

import json
from typing import Any, Iterator, Literal
from urllib.parse import urlsplit


class FixtureResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> FixtureResponse:
        return self

    def __exit__(self, *args: Any) -> Literal[False]:
        return False

    def iter_content(self, size: int) -> Iterator[bytes]:
        for offset in range(0, len(self.body), size):
            yield self.body[offset:offset + size]


class PaystackTransport:
    """Translate allowlisted synthetic HTTP requests into the shared provider fixture."""

    def __init__(self, backend: Any, secret: str) -> None:
        self.backend = backend
        self.secret = secret
        self.calls: list[tuple[str, str]] = []
        self.unavailable = False

    def request(self, session: Any, method: str, url: str, **kwargs: Any) -> FixtureResponse:
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and parsed.netloc == "api.paystack.co"
        assert not parsed.query and not parsed.fragment
        assert session.trust_env is False
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == (3, 8) and kwargs["stream"] is True
        assert kwargs["headers"]["Authorization"] == "Bearer " + self.secret
        path = parsed.path
        self.calls.append((method, path))  # No headers, credentials or customer bodies.
        if self.unavailable:
            return FixtureResponse({"status": False, "message": "Synthetic outage"}, 503)
        body = kwargs.get("json")
        if method == "GET" and path == "/plan/" + self.backend.plan_data["plan_code"]:
            data = self.backend.plan()
        elif method == "POST" and path == "/transaction/initialize":
            assert isinstance(body, dict)
            assert body["currency"] == "NGN" and body["amount"] == 750000
            assert body["plan"] == self.backend.plan_data["plan_code"]
            assert body["channels"] == ["card"]
            assert body["callback_url"] == "https://sandbox.example.test/billing/paystack/callback"
            data = self.backend.initialize(body["email"], body["reference"], body["plan"])
        elif method == "GET" and path.startswith("/transaction/verify/"):
            data = self.backend.verify(path.rsplit("/", 1)[1])
        elif method == "GET" and path == "/subscription":
            params = kwargs["params"]
            assert params["page"] == 1 and params["perPage"] == 100
            data = self.backend.subscriptions(params["customer"], params["plan"])
        elif method == "GET" and path.endswith("/manage/link"):
            data = {"link": self.backend.manage(path.split("/")[2])}
        elif method == "GET" and path.startswith("/subscription/"):
            data = self.backend.subscription(path.rsplit("/", 1)[1])
        elif method == "POST" and path == "/subscription/disable":
            assert isinstance(body, dict)
            self.backend.cancel(body["code"], body["token"])
            return FixtureResponse({"status": True, "message": "Subscription disabled"})
        elif method == "GET" and path.startswith("/transaction/"):
            data = self.backend.request(method, path)
        else:
            raise AssertionError(f"Unexpected fixture request: {method} {path}")
        return FixtureResponse({"status": True, "data": data})
