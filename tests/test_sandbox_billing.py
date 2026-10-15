"""Sandbox-only provider doubles; no credentials or requests to Paystack."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
import os
from threading import Thread

from alembic import command
import pytest
from sqlalchemy import inspect, text

from grid_monitor import _alembic_config, create_app
from grid_monitor.billing_models import BillingAccount, BillingEvent, BillingInvoice, BillingPayment
from grid_monitor.extensions import db
from grid_monitor.services import billing
from grid_monitor.services.paystack import BillingError, Paystack, provider_url
from grid_monitor.subscription_models import UserSubscription
from tests.billing_support import (
    BillingConfig, CALLBACK, CHECKOUT, PASSWORD, PLAN, SECRET, WEBHOOK,
    activation, checkout, drain, is_pro, post, renewal, sign_in, signed,
)

def test_checkout_requires_identity_csrf_and_server_owned_price(billing_app):
    client = billing_app.test_client()
    assert client.post(CHECKOUT).status_code == 401
    sign_in(client, "unverified")
    assert client.post(CHECKOUT).status_code == 403
    client = billing_app.test_client()
    sign_in(client)
    assert client.post(CHECKOUT).status_code == 400
    for values in ({"amount": "1"}, {"currency": "USD"}, {"plan": "PLN_fake"}, {"callback_url": "https://evil.test"}):
        assert post(client, CHECKOUT, **values).status_code == 400
    assert post(client, CHECKOUT).status_code == 303
    assert post(client, CHECKOUT).status_code == 303  # resumes the same checkout, never initializes twice
    fake = billing_app.extensions["billing_fake"]
    assert len([call for call in fake.calls if call[0] == "initialize"]) == 1
    with billing_app.app_context():
        contract = UserSubscription.query.filter_by(provider="paystack_test").one()
        assert (contract.currency, contract.billing_amount_minor, contract.status) == ("NGN", 750000, "pending")
        assert BillingPayment.query.count() == 0
    assert not is_pro(billing_app)


def test_callback_is_not_payment_proof_and_is_owner_scoped(billing_app):
    client, ref = checkout(billing_app)
    assert client.get(CALLBACK + "?reference=" + ref + "&reference=other").status_code == 400
    assert client.get(CALLBACK + "?reference=" + ref + "&trxref=other").status_code == 400
    other = billing_app.test_client()
    sign_in(other, "other")
    assert other.get(CALLBACK + "?reference=" + ref).status_code == 404
    assert client.get(CALLBACK + "?reference=" + ref).status_code == 303
    assert not is_pro(billing_app)
    drain(billing_app)
    assert is_pro(billing_app)
    with billing_app.app_context():
        assert BillingPayment.query.count() == 1
        assert BillingPayment.query.one().transaction_id == str(2**63 + 42)


@pytest.mark.parametrize("signature", ["", "forged", "a"*128, "\u2603"*128])
def test_forged_webhook_never_queues_or_grants(billing_app, signature):
    response = billing_app.test_client().post(WEBHOOK, data=b'{"event":"charge.success"}',
                                             headers={"x-paystack-signature": signature})
    assert response.status_code == 401
    with billing_app.app_context():
        assert BillingEvent.query.count() == 0
    assert not is_pro(billing_app)


def test_duplicate_and_semantic_replay_do_not_extend_period(billing_app):
    client, ref = activation(billing_app)
    event = {"event": "charge.success", "data": {"domain": "test", "reference": ref,
             "authorization": {"authorization_code": "never-store"}, "email_token": "never-store"}}
    first = signed(client, event)
    assert first.json == {"ok": True, "queued": True}
    assert signed(client, event).json["queued"] is False
    assert signed(client, event, pretty=True).json["queued"] is True
    with billing_app.app_context():
        end = BillingPayment.query.one().period_end
    drain(billing_app)
    with billing_app.app_context():
        assert BillingPayment.query.count() == 1
        assert BillingPayment.query.one().period_end == end
        assert "never-store" not in json.dumps([row.payload for row in BillingEvent.query.all()])
    billing_app.extensions["billing_clock"][0] += timedelta(days=35)
    assert signed(client, event).json["queued"] is False
    assert not is_pro(billing_app)


@pytest.mark.parametrize("field,value", [("currency", "USD"), ("amount", 1), ("amount", 750000.0),
                                         ("domain", "live"), ("reference", "other")])
def test_verified_api_mismatch_fails_closed(billing_app, field, value):
    client, ref = checkout(billing_app)
    billing_app.extensions["billing_fake"].transactions[ref][field] = value
    client.get(CALLBACK + "?reference=" + ref)
    with billing_app.app_context():
        assert billing.process_one()
        assert BillingEvent.query.one().status == "review"
        assert BillingPayment.query.count() == 0
    assert not is_pro(billing_app)


def test_unrelated_customer_or_subscription_cannot_be_adopted(billing_app):
    client, ref = checkout(billing_app)
    fake = billing_app.extensions["billing_fake"]
    fake.sub["authorization"]["authorization_code"] = "AUTH_unrelated"
    client.get(CALLBACK + "?reference=" + ref)
    with billing_app.app_context():
        billing.process_one()
        assert BillingPayment.query.count() == 0
    assert not is_pro(billing_app)


def test_subscription_create_before_charge_uses_original_transaction(billing_app):
    client, _ = checkout(billing_app)
    event = {"event": "subscription.create", "data": {"domain": "test", "subscription_code": "SUB_synthetic"}}
    assert signed(client, event).status_code == 200
    drain(billing_app)
    assert is_pro(billing_app)


def test_failed_initial_payment_then_recovery(billing_app):
    client, ref = checkout(billing_app)
    tx = billing_app.extensions["billing_fake"].transactions[ref]
    tx.update(status="failed", paid_at=None)
    client.get(CALLBACK + "?reference=" + ref)
    drain(billing_app)
    assert not is_pro(billing_app)
    assert post(client, CHECKOUT).status_code == 303
    tx.update(status="success", paid_at=billing_app.extensions["billing_clock"][0].isoformat())
    assert post(client, "/billing/paystack/refresh").status_code == 303
    drain(billing_app)
    assert is_pro(billing_app)
    with billing_app.app_context():
        assert BillingPayment.query.count() == 1


def test_renewal_invoice_charge_and_out_of_order_failure(billing_app):
    client, _ = activation(billing_app)
    invoice = renewal(billing_app)
    assert not is_pro(billing_app)  # previous period has expired
    assert signed(client, {"event": "invoice.update", "data": invoice}).status_code == 200
    drain(billing_app)
    assert is_pro(billing_app)
    failed = deepcopy(invoice)
    failed.update(paid=False, status="failed", transaction=None)
    assert signed(client, {"event": "invoice.payment_failed", "data": failed}).status_code == 200
    drain(billing_app)
    assert is_pro(billing_app)
    with billing_app.app_context():
        assert BillingPayment.query.count() == 2
        assert BillingInvoice.query.one().status == "paid"
    # Same verified transaction cannot be reused to purchase another period.
    replay = deepcopy(invoice)
    start = billing.timestamp(replay["period_start"]) + timedelta(days=28)
    replay.update(invoice_code="INV_replayed", period_start=start.isoformat(),
                  period_end=(start + timedelta(days=28)).isoformat())
    signed(client, {"event": "invoice.update", "data": replay})
    with billing_app.app_context():
        billing.process_one()
        assert BillingInvoice.query.count() == 1


def test_failed_renewal_expiry_and_later_recovery(billing_app):
    client, _ = activation(billing_app)
    failed = renewal(billing_app, paid=False)
    signed(client, {"event": "invoice.payment_failed", "data": failed})
    drain(billing_app)
    assert not is_pro(billing_app)
    with billing_app.app_context():
        contract = UserSubscription.query.filter_by(provider="paystack_test").one()
        assert contract.status == "past_due"
        assert BillingInvoice.query.one().status == "failed"
    fake, clock = billing_app.extensions["billing_fake"], billing_app.extensions["billing_clock"]
    recovered = deepcopy(failed)
    ref = "recovered-synthetic"
    tx = deepcopy(next(iter(fake.transactions.values())))
    tx.update(id=tx["id"] + 1, reference=ref, paid_at=clock[0].isoformat())
    fake.transactions[ref] = tx
    recovered.update(paid=True, status="success", transaction={"reference": ref, "id": tx["id"]})
    fake.sub.update(status="active", invoices=[recovered], updatedAt=clock[0].isoformat())
    signed(client, {"event": "invoice.update", "data": recovered})
    drain(billing_app)
    assert is_pro(billing_app)


def test_cancellation_preserves_paid_period_and_recovery_uses_current_api(billing_app):
    client, _ = activation(billing_app)
    assert post(client, "/billing/paystack/cancel").status_code == 303
    drain(billing_app)
    assert is_pro(billing_app)
    with billing_app.app_context():
        account = BillingAccount.query.one()
        assert not account.renewal_enabled
        assert account.cancel_requested_at is not None
        assert UserSubscription.query.filter_by(provider="paystack_test").one().status == "cancelled"
    assert post(client, "/billing/paystack/manage").headers["Location"].startswith("https://paystack.com/manage/")
    fake, clock = billing_app.extensions["billing_fake"], billing_app.extensions["billing_clock"]
    clock[0] += timedelta(minutes=10)
    fake.sub.update(status="active", updatedAt=clock[0].isoformat())
    # Late cancellation notification must not overwrite provider-confirmed recovery.
    signed(client, {"event": "subscription.disable", "data": {"domain": "test", "subscription_code": "SUB_synthetic"}})
    drain(billing_app)
    with billing_app.app_context():
        assert BillingAccount.query.one().renewal_enabled
        assert BillingAccount.query.one().cancel_requested_at is None
    clock[0] += timedelta(days=35)
    assert not is_pro(billing_app)


def test_database_flag_without_verified_ledger_never_grants_sandbox_pro(billing_app):
    client, _ = checkout(billing_app)
    with billing_app.app_context():
        contract = UserSubscription.query.filter_by(provider="paystack_test").one()
        now = billing_app.extensions["billing_clock"][0]
        contract.status, contract.current_period_start, contract.current_period_end = "active", now, now + timedelta(days=28)
        db.session.commit()
    assert not is_pro(billing_app)


def test_disabling_sandbox_revokes_test_entitlements_but_not_public_access(billing_app):
    client, _ = activation(billing_app)
    assert is_pro(billing_app)
    billing_app.config["PAYSTACK_TEST_CHECKOUT_ENABLED"] = False
    assert not is_pro(billing_app)
    assert client.post(CHECKOUT).status_code == 404
    assert client.post(WEBHOOK).status_code == 404
    assert client.get("/account/billing").status_code == 200
    for path in ("/states", "/state/lagos", "/region/north-central", "/research", "/articles"):
        assert client.get(path).status_code == 200


def test_provider_outage_is_durable_and_no_blind_reinitialization(billing_app):
    fake = billing_app.extensions["billing_fake"]
    fake.fail = True
    client = billing_app.test_client()
    sign_in(client)
    assert post(client, CHECKOUT).status_code == 503
    assert post(client, CHECKOUT).status_code == 409
    with billing_app.app_context():
        assert BillingAccount.query.one().checkout_status == "review"
        assert BillingEvent.query.count() == 1
    assert len([call for call in fake.calls if call[0] == "initialize"]) == 1


def test_concurrent_callbacks_and_webhooks_apply_once(billing_app):
    client, ref = checkout(billing_app)
    def deliver(index):
        with billing_app.app_context():
            return billing.enqueue_internal("verify", {"reference": ref}, "concurrent:" + ref)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(deliver, range(12)))
    assert sum(results) == 1
    def process(index):
        with billing_app.app_context():
            return billing.process_one()
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(process, range(8)))
    drain(billing_app)
    assert is_pro(billing_app)
    with billing_app.app_context():
        assert BillingPayment.query.count() == 1
        assert BillingAccount.query.one().lease_token is None


def test_expired_worker_lease_and_deferred_event_recover(billing_app):
    client, ref = checkout(billing_app)
    client.get(CALLBACK + "?reference=" + ref)
    with billing_app.app_context():
        event = BillingEvent.query.one()
        event.status, event.lease_token = "processing", "crashed-worker"
        event.available_at = billing_app.extensions["billing_clock"][0] - timedelta(seconds=1)
        account = BillingAccount.query.one()
        account.lease_token, account.lease_until = "crashed-worker", event.available_at
        db.session.commit()
    drain(billing_app)
    assert is_pro(billing_app)


@pytest.mark.parametrize("overrides", [
    {"LIVE_BILLING_ENABLED": True}, {"USD_CHECKOUT_ENABLED": True},
    {"PAYSTACK_SECRET_KEY": "sk_live_" + "x" * 32},
    {"BILLING_ENVIRONMENT": "production"},
    {"APP_BASE_URL": "https://nigeriapowerdata.com", "PAYSTACK_SANDBOX_ORIGIN": "https://nigeriapowerdata.com"},
    {"PAYSTACK_SANDBOX_ORIGIN": "https://evil.example"},
    {"PAYSTACK_NGN_PRO_PLAN_CODE": ""}, {"PAYSTACK_TEST_INTEGRATION_ID": ""},
])
def test_unsafe_sandbox_configuration_rejected(overrides):
    with pytest.raises(RuntimeError):
        create_app(type("InvalidSandbox", (BillingConfig,), overrides))


@pytest.mark.parametrize("url", ["http://checkout.paystack.com/test", "https://checkout.paystack.com.evil.test/x",
                                 "https://user:pass@checkout.paystack.com/x", "https://evil.test"])
def test_external_redirects_are_allowlisted(url):
    with pytest.raises(BillingError):
        provider_url(url, "checkout")


def test_provider_initialize_controls_all_money_and_callback_fields(billing_app, monkeypatch):
    calls = []
    monkeypatch.setattr(Paystack, "request", lambda self, method, path, **kwargs: calls.append((method, path, kwargs)))
    with billing_app.app_context():
        Paystack().initialize("customer@example.com", "server-reference", PLAN)
    body = calls[0][2]["payload"]
    assert body == {"email": "customer@example.com", "reference": "server-reference", "plan": PLAN,
                    "amount": 750000, "currency": "NGN", "channels": ["card"],
                    "callback_url": "https://sandbox.example.test/billing/paystack/callback"}


def test_dashboard_is_private_and_never_exposes_secrets(billing_app):
    client, _ = activation(billing_app)
    response = client.get("/account/billing", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "private" in response.headers["Cache-Control"] and "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert "Content-Encoding" not in response.headers
    html = response.get_data(as_text=True)
    for secret in (SECRET, "sensitive-never-stored", "AUTH_synthetic", "gtag(", "clarity("):
        assert secret not in html
    assert "7500" not in html or "7,500" in html
    assert "Success" in html and "Cancel renewal" in html
    other = billing_app.test_client()
    sign_in(other, "other")
    assert "No verified payments yet" in other.get("/account/billing").get_data(as_text=True)


def test_billing_browser_responsive_and_no_console_errors(billing_app):
    from playwright.sync_api import sync_playwright
    activation(billing_app)
    server = __import__("werkzeug.serving", fromlist=["make_server"]).make_server("127.0.0.1", 0, billing_app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            base = f"http://127.0.0.1:{server.server_port}"
            page.goto(base + "/login")
            page.locator("#email").fill("customer@example.com")
            page.locator("#password").fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.wait_for_url("**/account")
            for width in (1440, 768, 390, 320):
                page.set_viewport_size({"width": width, "height": 1000})
                response = page.goto(base + "/account/billing", wait_until="networkidle")
                assert response.status == 200
                assert page.get_by_role("heading", name="Subscription and billing").is_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            # Our application pages must have no browser errors before leaving the site.
            # The external provider's console and favicon/network policies are not ours.
            assert errors == [], f"Billing dashboard browser errors: {errors}"
            # Keep this browser test focused on the local, responsive billing UI.
            # Actual POST/CSRF and allowlisted 303 Location redirects are verified
            # by test_dashboard_is_private_and_never_exposes_secrets and the
            # billing lifecycle tests; do not navigate to an external origin here.
            manage_form = page.locator('form[action="/billing/paystack/manage"]')
            assert manage_form.count() == 1
            csrf_field = manage_form.locator('input[name="csrf_token"]')
            assert csrf_field.count() == 1
            assert csrf_field.input_value()
            assert manage_form.get_by_role(
                "button", name="Manage renewal / payment method", exact=True
            ).is_visible()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_migration_schema_and_non_destructive_rollback(tmp_path):
    uri = os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL") or "sqlite:///" + str(tmp_path / "billing-migration.sqlite")
    config = type("MigrationBilling", (BillingConfig,), {
        "ACCOUNTS_ENABLED": False, "PAYSTACK_TEST_CHECKOUT_ENABLED": False,
        "PREMIUM_GATING_ENABLED": False, "AUTO_CREATE_TABLES": False,
        "SQLALCHEMY_DATABASE_URI": uri, "SQLALCHEMY_ENGINE_OPTIONS": {},
    })
    app = create_app(config)
    with app.app_context():
        db.drop_all()
        db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()
        command.upgrade(_alembic_config(app), "head")
        for model in (BillingAccount, BillingPayment, BillingInvoice, BillingEvent):
            actual = {col["name"] for col in inspect(db.engine).get_columns(model.__tablename__)}
            assert actual == set(model.__table__.columns.keys())
        command.downgrade(_alembic_config(app), "d13a20261013")
        assert "users" in inspect(db.engine).get_table_names()
        assert "grid_snapshots" in inspect(db.engine).get_table_names()
        assert "billing_payments" not in inspect(db.engine).get_table_names()
        command.upgrade(_alembic_config(app), "head")
        billing.enqueue_internal("reconcile", {"user_id": 999}, "migration-retention")
        with pytest.raises(RuntimeError, match="Non-destructive rollback"):
            command.downgrade(_alembic_config(app), "d13a20261013")
        db.session.rollback()
        assert BillingEvent.query.count() == 1
        db.session.rollback()
        db.drop_all()
        db.session.execute(text("DROP TABLE alembic_version"))
        db.session.commit()


def test_invalid_invoice_never_changes_paid_through(billing_app):
    client, _ = activation(billing_app)
    invoice = renewal(billing_app)
    invoice["period_end"] = invoice["period_start"]
    signed(client, {"event": "invoice.update", "data": invoice})
    with billing_app.app_context():
        billing.process_one()
        assert BillingEvent.query.filter_by(status="review").count() == 1
        assert BillingPayment.query.count() == 1
    assert not is_pro(billing_app)


def test_account_lease_serializes_different_events(billing_app):
    client, ref = checkout(billing_app)
    client.get(CALLBACK + "?reference=" + ref)
    signed(client, {"event": "subscription.create", "data": {"domain": "test", "subscription_code": "SUB_synthetic"}})
    def process(_):
        with billing_app.app_context():
            return billing.process_one()
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(process, range(2)))
    billing_app.extensions["billing_clock"][0] += timedelta(minutes=2)
    drain(billing_app)
    assert is_pro(billing_app)
    with billing_app.app_context():
        assert BillingPayment.query.count() == 1


def test_invoice_create_does_not_grant_unpaid_future_period(billing_app):
    client, _ = activation(billing_app)
    fake = billing_app.extensions["billing_fake"]
    start = billing.timestamp(fake.sub["next_payment_date"])
    invoice = {"domain": "test", "invoice_code": "INV_future", "amount": 750000,
        "period_start": start.isoformat(), "period_end": (start + timedelta(days=28)).isoformat(),
        "status": "pending", "paid": False, "subscription": {"subscription_code": "SUB_synthetic"}}
    signed(client, {"event": "invoice.create", "data": invoice})
    drain(billing_app)
    with billing_app.app_context():
        assert BillingPayment.query.count() == 1
        assert BillingInvoice.query.one().status == "pending"
    billing_app.extensions["billing_clock"][0] = start + timedelta(seconds=1)
    assert not is_pro(billing_app)


def test_plan_mismatch_and_live_webhook_rejected(billing_app):
    client = billing_app.test_client()
    sign_in(client)
    billing_app.extensions["billing_fake"].plan_data["amount"] = 100
    assert post(client, CHECKOUT).status_code == 409
    with billing_app.app_context():
        assert BillingAccount.query.count() == 0
    response = signed(client, {"event": "charge.success", "data": {"domain": "live", "reference": "anything"}})
    assert response.status_code == 400


def test_stale_provider_response_cannot_reverse_cancellation(billing_app):
    client, _ = activation(billing_app)
    fake, clock = billing_app.extensions["billing_fake"], billing_app.extensions["billing_clock"]
    original = fake.sub["updatedAt"]
    clock[0] += timedelta(minutes=10)
    post(client, "/billing/paystack/cancel")
    drain(billing_app)
    fake.sub.update(status="active", updatedAt=original)
    post(client, "/billing/paystack/refresh")
    drain(billing_app)
    with billing_app.app_context():
        assert not BillingAccount.query.one().renewal_enabled
        assert UserSubscription.query.filter_by(provider="paystack_test").one().status == "cancelled"


def test_fast_webhook_cannot_be_overwritten_by_initialize_response(billing_app, monkeypatch):
    fake = billing_app.extensions["billing_fake"]
    original = fake.initialize
    def immediate(email, reference, plan):
        result = original(email, reference, plan)
        billing.enqueue_internal("verify", {"reference": reference}, "early:" + reference)
        assert billing.process_one()
        return result
    monkeypatch.setattr(fake, "initialize", immediate)
    client = billing_app.test_client()
    sign_in(client)
    response = post(client, CHECKOUT)
    assert response.status_code == 303 and response.headers["Location"] == "/account/billing"
    assert is_pro(billing_app)
    with billing_app.app_context():
        assert BillingAccount.query.one().checkout_status == "verified"
        assert BillingAccount.query.one().checkout_url is None


@pytest.mark.parametrize("command_name", ["billing-worker", "billing-status", "billing-retry"])
def test_billing_cli_does_not_start_unrelated_background_services(tmp_path, monkeypatch, command_name):
    import grid_monitor
    monkeypatch.setattr("sys.argv", ["flask", command_name])
    calls = []
    monkeypatch.setattr(grid_monitor, "start_scheduler", lambda app: calls.append("grid"))
    monkeypatch.setattr(grid_monitor, "start_indexnow_startup_notification", lambda app: calls.append("indexnow"))
    monkeypatch.setattr(grid_monitor, "start_mail_queue", lambda app: calls.append("mail"))
    config = type("BillingCli", (BillingConfig,), {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "cli.sqlite"),
        "SQLALCHEMY_ENGINE_OPTIONS": {}, "HISTORY_CAPTURE_ENABLED": True, "INDEXNOW_ENABLED": True,
    })
    app = create_app(config)
    assert calls == []
    with app.app_context():
        db.drop_all()


def test_documented_cancel_response_without_data_is_accepted(billing_app, monkeypatch, caplog):
    calls = []
    class Response:
        status_code = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def iter_content(self, size):
            yield b'{"status":true,"message":"Subscription disabled successfully"}'
    class Session:
        trust_env = True
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def request(self, method, url, **kwargs):
            assert self.trust_env is False
            calls.append((method, url, kwargs))
            return Response()
    monkeypatch.setattr("requests.Session", Session)
    with billing_app.app_context():
        assert Paystack().cancel("SUB_synthetic", "secret-email-token") is None
        with pytest.raises(BillingError, match="provider_response_invalid"):
            Paystack().verify("synthetic")
    method, url, options = calls[0]
    assert (method, url) == ("POST", "https://api.paystack.co/subscription/disable")
    assert options["allow_redirects"] is False and options["timeout"] == (3, 8)
    assert options["headers"]["Authorization"] == "Bearer " + SECRET
    assert SECRET not in caplog.text and "secret-email-token" not in caplog.text


def test_delayed_failure_prefers_provider_verified_paid_invoice(billing_app):
    client, _ = activation(billing_app)
    invoice = renewal(billing_app)
    failed = deepcopy(invoice)
    failed.update(paid=False, status="failed", transaction=None)
    signed(client, {"event": "invoice.payment_failed", "data": failed})
    drain(billing_app)
    assert is_pro(billing_app)
    with billing_app.app_context():
        assert BillingInvoice.query.one().status == "paid"
        assert BillingPayment.query.count() == 2
