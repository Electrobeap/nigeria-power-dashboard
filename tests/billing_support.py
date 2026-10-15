"""Shared test-only billing doubles and fixtures; never imported by the application."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os

from bs4 import BeautifulSoup
import pytest

from grid_monitor import create_app
from grid_monitor.billing_models import BillingAccount, BillingEvent
from grid_monitor.config import Config
from grid_monitor.extensions import db
from grid_monitor.services import billing
from grid_monitor.services.entitlements import active_subscription
from grid_monitor.services.paystack import BillingError, validate_plan
from grid_monitor.services.subscriptions import seed_subscription_pricing
from grid_monitor.subscription_models import User, UserSubscription, utc_now

SECRET = "sk_test_" + "synthetic1234" * 4
PLAN = "PLN_synthetic"
PASSWORD = "Synthetic billing test passphrase"
WEBHOOK = "/api/billing/paystack/webhook"
CALLBACK = "/billing/paystack/callback"
CHECKOUT = "/billing/paystack/checkout"


class BillingConfig(Config):
    TESTING = True
    SECRET_KEY = "synthetic-billing-session-key-at-least-32-characters"
    ACCOUNTS_ENABLED = True
    SUBSCRIPTIONS_ENABLED = True
    PREMIUM_GATING_ENABLED = True
    PRO_PREVIEW_ENABLED = True
    PAYSTACK_TEST_CHECKOUT_ENABLED = True
    LIVE_BILLING_ENABLED = False
    USD_CHECKOUT_ENABLED = False
    BILLING_ENVIRONMENT = "staging"
    APP_BASE_URL = "https://sandbox.example.test"
    PAYSTACK_SANDBOX_ORIGIN = APP_BASE_URL
    PAYSTACK_SECRET_KEY = SECRET
    PAYSTACK_NGN_PRO_PLAN_CODE = PLAN
    PAYSTACK_TEST_INTEGRATION_ID = "123456"
    AUTH_EMAIL_ENABLED = False
    AUTH_EMAIL_VERIFICATION_REQUIRED = False
    SESSION_COOKIE_SECURE = False
    RUN_MIGRATIONS_ON_STARTUP = False
    AUTO_CREATE_TABLES = True
    HISTORY_CAPTURE_ENABLED = False
    WEB_SCHEDULER_ENABLED = False
    INDEXNOW_ENABLED = False
    INDEXNOW_AUTO_NOTIFY_ENABLED = False


class FakePaystack:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.transactions = {}
        self.plan_data = {"domain": "test", "integration": 123456, "id": 10, "plan_code": PLAN,
                          "currency": "NGN", "amount": 750000, "interval": "monthly"}
        self.sub = None
        self.fail = False

    def plan(self):
        return validate_plan(deepcopy(self.plan_data))

    def initialize(self, email, reference, plan):
        self.calls.append(("initialize", email, reference, plan))
        if self.fail:
            raise BillingError()
        paid = self.clock[0]
        self.transactions[reference] = {"id": 2**63 + 42, "reference": reference, "domain": "test",
            "status": "success", "amount": 750000, "currency": "NGN", "paid_at": paid.isoformat(),
            "customer": {"id": 20, "email": email, "customer_code": "CUS_synthetic"},
            "authorization": {"authorization_code": "AUTH_synthetic"}}
        self.sub = {"domain": "test", "integration": 123456, "plan": deepcopy(self.plan_data),
            "customer": deepcopy(self.transactions[reference]["customer"]), "amount": 750000,
            "authorization": {"authorization_code": "AUTH_synthetic"},
            "subscription_code": "SUB_synthetic", "status": "active", "email_token": "sensitive-never-stored",
            "createdAt": paid.isoformat(), "updatedAt": paid.isoformat(),
            "next_payment_date": (paid + timedelta(days=28)).isoformat(), "invoices": []}
        return {"reference": reference, "authorization_url": "https://checkout.paystack.com/synthetic"}

    def verify(self, reference):
        self.calls.append(("verify", reference))
        if self.fail:
            raise BillingError()
        return deepcopy(self.transactions[reference])

    def subscriptions(self, customer_id, plan_id):
        return [deepcopy(self.sub)]

    def subscription(self, code):
        assert code == "SUB_synthetic"
        return deepcopy(self.sub)

    def cancel(self, code, token):
        assert code == "SUB_synthetic" and token == "sensitive-never-stored"
        self.calls.append(("cancel", code))
        self.sub["status"] = "non-renewing"
        self.sub["updatedAt"] = self.clock[0].isoformat()

    def manage(self, code):
        assert code == "SUB_synthetic"
        return "https://paystack.com/manage/subscriptions/synthetic?subscription_token=sensitive"

    def request(self, method, path, **kwargs):
        assert method == "GET" and path.startswith("/transaction/")
        txn_id = path.rsplit("/", 1)[1]
        return deepcopy(next(value for value in self.transactions.values() if str(value["id"]) == txn_id))


@pytest.fixture()
def billing_epoch():
    """Legacy tests use real time; lifecycle tests override with a fixed UTC epoch."""
    return None


@pytest.fixture()
def billing_app(tmp_path, monkeypatch, billing_epoch):
    uri = os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL") or "sqlite:///" + str(tmp_path / "billing.sqlite")
    config = type("IsolatedBillingConfig", (BillingConfig,), {
        "SQLALCHEMY_DATABASE_URI": uri, "SAFE_DATABASE_URI": "isolated-billing-test-db",
        "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"check_same_thread": False, "timeout": 20}} if uri.startswith("sqlite:") else {},
    })
    clock = [billing_epoch or utc_now()]
    if billing_epoch is not None:
        class FrozenAccountDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

        # Covers model defaults and imported account utc_now callables without
        # freezing browser/thread timeouts or changing application code.
        monkeypatch.setattr("grid_monitor.subscription_models.datetime", FrozenAccountDateTime)
    monkeypatch.setattr(billing, "utc_now", lambda: clock[0])
    monkeypatch.setattr("grid_monitor.services.entitlements.utc_now", lambda: clock[0])
    fake = FakePaystack(clock)
    monkeypatch.setattr(billing, "provider", lambda: fake)
    monkeypatch.setattr("grid_monitor.routes.billing.provider", lambda: fake)
    # A missed double must fail instead of making any network request.
    monkeypatch.setattr("requests.Session.request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Unexpected provider network")))
    app = create_app(config)
    assert app.testing, "Provider doubles may only be attached to isolated test applications."
    app.extensions.update(billing_fake=fake, billing_clock=clock)
    with app.app_context():
        seed_subscription_pricing()
        template = User(email="template@example.com")
        template.set_password(PASSWORD)
        ids = {}
        for name in ("customer", "other", "unverified"):
            user = User(email=name + "@example.com", password_hash=template.password_hash,
                        email_verified_at=None if name == "unverified" else clock[0])
            db.session.add(user)
            db.session.flush()
            ids[name] = user.id
            db.session.add(UserSubscription(user_id=user.id, plan_code="community", status="free",
                                           currency="NGN", billing_amount_minor=0))
        db.session.commit()
        app.extensions["billing_users"] = ids
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def sign_in(client, name="customer"):
    token = BeautifulSoup(client.get("/login").data, "html.parser").select_one('input[name="csrf_token"]')["value"]
    response = client.post("/login", data={"email": name + "@example.com", "password": PASSWORD, "csrf_token": token})
    assert response.status_code == 303


def post(client, path, **values):
    token = BeautifulSoup(client.get("/account/billing").data, "html.parser").select_one('input[name="csrf_token"]')["value"]
    return client.post(path, data={"csrf_token": token, **values})


def checkout(app):
    client = app.test_client()
    sign_in(client)
    assert post(client, CHECKOUT).status_code == 303
    with app.app_context():
        ref = db.session.get(BillingAccount, app.extensions["billing_users"]["customer"]).checkout_reference
    return client, ref


def drain(app):
    with app.app_context():
        for _ in range(30):
            if not billing.process_one():
                break
        errors = [(row.event_type, row.status, row.last_error) for row in BillingEvent.query.all() if row.status != "processed"]
        assert not errors, errors


def signed(client, event, *, pretty=False):
    raw = json.dumps(event, indent=2 if pretty else None).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()
    return client.post(WEBHOOK, data=raw, content_type="application/json", headers={"x-paystack-signature": signature})


def activation(app):
    client, ref = checkout(app)
    assert client.get(CALLBACK + "?reference=" + ref).status_code == 303
    drain(app)
    return client, ref


def is_pro(app):
    with app.app_context():
        user = db.session.get(User, app.extensions["billing_users"]["customer"])
        return active_subscription(user) is not None


def renewal(app, *, paid=True):
    fake, clock = app.extensions["billing_fake"], app.extensions["billing_clock"]
    start = billing.timestamp(fake.sub["next_payment_date"])
    end = start + timedelta(days=28)
    clock[0] = start + timedelta(minutes=2)
    ref = "renewal-synthetic-" + str(len(fake.transactions))
    tx = deepcopy(next(iter(fake.transactions.values())))
    tx.update(id=tx["id"] + len(fake.transactions), reference=ref, paid_at=clock[0].isoformat())
    if paid:
        fake.transactions[ref] = tx
    invoice = {"domain": "test", "invoice_code": "INV_" + ref, "amount": 750000,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "status": "success" if paid else "failed", "paid": paid,
        "paid_at": clock[0].isoformat() if paid else None,
        "subscription": {"subscription_code": "SUB_synthetic"},
        "transaction": {"id": tx["id"], "reference": ref} if paid else None}
    fake.sub.update(status="active" if paid else "attention", updatedAt=clock[0].isoformat(),
                    next_payment_date=end.isoformat(), invoices=[invoice])
    return invoice

