"""Stage D1: HTTP -> real adapter -> worker -> ledger -> premium API, without Paystack."""
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
import pytest
from sqlalchemy import select

from grid_monitor import create_app
from grid_monitor.billing_models import BillingAccount, BillingEvent, BillingInvoice, BillingPayment
from grid_monitor.extensions import db
from grid_monitor.models import GridSnapshot
from grid_monitor.services import billing, paystack
from grid_monitor.services.cache import clear_cache
from grid_monitor.services.geographic_hierarchy import hierarchy_nodes
from grid_monitor.subscription_models import User
from tests.billing_support import (
    BillingConfig, CALLBACK, CHECKOUT, PASSWORD, SECRET, WEBHOOK,
    activation, checkout, drain, post, renewal, sign_in, signed,
)
from tests.billing_transport import PaystackTransport

REPORT = "/api/pro/generation-analysis"
EXPORT = "/api/pro/exports/generation.csv"
WINDOW = "?start=2024-01-01&end=2024-01-03"
EPOCH = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def billing_epoch():
    return EPOCH


@pytest.fixture()
def lifecycle_app(billing_app, monkeypatch):
    """Keep the real adapter, signatures, routes, worker, DB and guards in the loop."""
    clear_cache()
    transport = PaystackTransport(billing_app.extensions["billing_fake"], SECRET)
    monkeypatch.setattr(billing, "provider", paystack.provider)
    monkeypatch.setattr("grid_monitor.routes.billing.provider", paystack.provider)
    monkeypatch.setattr(
        "requests.Session.request",
        lambda session, method, url, **kwargs: transport.request(session, method, url, **kwargs),
    )
    billing_app.extensions["billing_transport"] = transport
    with billing_app.app_context():
        for hour, mw in ((0, 4000), (12, 4200)):
            stamp = datetime(2024, 1, 1, hour, tzinfo=timezone.utc)
            db.session.add(GridSnapshot(
                reading_timestamp=stamp, captured_at=stamp, total_generation_mw=mw,
                source="synthetic D1 observation", daily_json={},
                raw_payload_json={"sentinel": "unchanged-energy-history"},
            ))
        db.session.commit()
    yield billing_app
    clear_cache()


def premium(client, status):
    for path in (REPORT, EXPORT):
        response = client.get(path + WINDOW)
        assert response.status_code == status, (path, response.get_data(as_text=True))
        assert client.head(path + WINDOW).status_code == status
        assert "no-store" in response.headers["Cache-Control"]
        assert "private" in response.headers["Cache-Control"]
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
        if status == 200 and path == REPORT:
            assert response.json["data"]["coverage"]["stored_readings"] == 2
            assert response.json["data"]["daily"][0]["mean_generation_mw"] == 4100
        elif status == 200:
            assert response.mimetype == "text/csv"
            assert "4100" in response.get_data(as_text=True)
        else:
            assert not response.json["ok"]
            assert "attachment" not in response.headers.get("Content-Disposition", "")


def plan(client):
    response = client.get("/account/billing")
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    return {label.get_text(strip=True): label.find_next_sibling("dd").get_text(" ", strip=True)
            for label in soup.select("dl.account-details dt")}


def reauthenticate(app, name="customer"):
    client = app.test_client()
    sign_in(client, name)
    return client


def charge(reference):
    return {"event": "charge.success", "data": {"domain": "test", "reference": reference}}


def ledger(app):
    with app.app_context():
        return list(db.session.execute(select(
            BillingPayment.transaction_id, BillingPayment.reference, BillingPayment.status,
            BillingPayment.period_start, BillingPayment.period_end,
        ).order_by(BillingPayment.id)))


def energy_rows(app):
    with app.app_context():
        return list(db.session.execute(select(
            GridSnapshot.id, GridSnapshot.reading_timestamp,
            GridSnapshot.total_generation_mw, GridSnapshot.raw_payload_json,
        ).order_by(GridSnapshot.id)))


def test_checkout_to_verified_pro_via_worker_and_http_guards(lifecycle_app):
    app = lifecycle_app
    before = energy_rows(app)
    premium(app.test_client(), 401)
    client = reauthenticate(app)
    premium(client, 403)
    assert plan(client)["Plan"] == "Community"
    assert post(client, CHECKOUT).status_code == 303
    with app.app_context():
        account = BillingAccount.query.one()
        assert billing.aware(account.created_at) == EPOCH
        reference = account.checkout_reference
    premium(client, 403)
    assert client.get(CALLBACK + "?reference=" + reference).status_code == 303
    assert signed(client, charge(reference)).json["queued"]
    premium(client, 403)  # Authentic notification and browser callback are not payment proof.
    assert ledger(app) == []
    result = app.test_cli_runner().invoke(args=["billing-worker", "--once"])
    assert result.exit_code == 0, result.output
    premium(client, 200)
    assert plan(client)["Plan"] == "Pro (sandbox)"
    assert plan(client)["Paid through"] == "12 Feb 2026, 12:00 UTC"
    assert len(ledger(app)) == 1
    assert ledger(app)[0][2] == "success"
    assert ("GET", "/transaction/verify/" + reference) in app.extensions["billing_transport"].calls
    premium(reauthenticate(app, "other"), 403)
    premium(reauthenticate(app, "unverified"), 403)
    premium(app.test_client(), 401)
    assert energy_rows(app) == before


@pytest.mark.parametrize("provider_status", ["failed", "abandoned"])
def test_unsuccessful_initial_charge_never_grants_and_recovery_is_verified(lifecycle_app, provider_status):
    app = lifecycle_app
    client, reference = checkout(app)
    transaction = app.extensions["billing_fake"].transactions[reference]
    transaction.update(status=provider_status, paid_at=None)
    assert signed(client, charge(reference)).status_code == 200
    drain(app)
    premium(client, 403)
    assert plan(client)["Plan"] == "Community"
    assert ledger(app)[0][2] == "failed"
    transaction.update(status="success", paid_at=EPOCH.isoformat())
    assert post(client, "/billing/paystack/refresh").status_code == 303
    premium(client, 403)
    drain(app)
    premium(client, 200)
    assert len(ledger(app)) == 1 and ledger(app)[0][2] == "success"


def test_provider_outage_defers_without_grant_then_recovers(lifecycle_app):
    app = lifecycle_app
    client, reference = checkout(app)
    app.extensions["billing_transport"].unavailable = True
    assert signed(client, charge(reference)).status_code == 200
    with app.app_context():
        assert billing.process_one()
        event = BillingEvent.query.one()
        assert event.status == "pending" and event.attempts == 1
        assert event.last_error == "provider_unavailable"
        retry_at = billing.aware(event.available_at)
    premium(client, 403)
    assert ledger(app) == []
    app.extensions["billing_transport"].unavailable = False
    app.extensions["billing_clock"][0] = retry_at
    drain(app)
    premium(client, 200)


def test_renewal_boundary_failed_invoice_and_verified_recovery(lifecycle_app):
    app = lifecycle_app
    client, _ = activation(app)
    premium(client, 200)
    failed = renewal(app, paid=False)
    client = reauthenticate(app)  # Normal eight-hour sessions still expire.
    premium(client, 403)  # No grace access while reconciliation is delayed.
    assert signed(client, {"event": "invoice.payment_failed", "data": failed}).status_code == 200
    drain(app)
    premium(client, 403)
    assert plan(client)["Status"] == "Past Due"
    assert plan(client)["Plan"] == "Community"
    fake = app.extensions["billing_fake"]
    now = app.extensions["billing_clock"][0]
    recovered = deepcopy(failed)
    tx = deepcopy(next(iter(fake.transactions.values())))
    tx.update(id=tx["id"] + 1, reference="renewal-recovery-d1", paid_at=now.isoformat())
    fake.transactions[tx["reference"]] = tx
    recovered.update(paid=True, status="success", transaction={"id": tx["id"], "reference": tx["reference"]})
    fake.sub.update(status="active", updatedAt=now.isoformat(), invoices=[recovered])
    assert signed(client, {"event": "invoice.update", "data": recovered}).status_code == 200
    premium(client, 403)
    drain(app)
    premium(client, 200)
    paid_ledger = ledger(app)
    assert len(paid_ledger) == 2
    assert signed(client, {"event": "invoice.payment_failed", "data": failed}).json["queued"] is False
    assert signed(client, {"event": "invoice.payment_failed", "data": failed}, pretty=True).json["queued"]
    drain(app)
    premium(client, 200)
    assert ledger(app) == paid_ledger
    with app.app_context():
        assert BillingInvoice.query.one().status == "paid"


def test_successful_renewal_out_of_order_events_do_not_double_credit(lifecycle_app):
    app = lifecycle_app
    client, initial_ref = activation(app)
    invoice = renewal(app)
    client = reauthenticate(app)
    premium(client, 403)
    for payload in (
        charge(invoice["transaction"]["reference"]),
        {"event": "invoice.update", "data": invoice},
        charge(initial_ref),
        {"event": "subscription.create", "data": {"domain": "test", "subscription_code": "SUB_synthetic"}},
    ):
        assert signed(client, payload).status_code == 200
    drain(app)
    premium(client, 200)
    assert len(ledger(app)) == 2
    first, second = ledger(app)
    assert first[4] == second[3]
    assert plan(client)["Next billing"] == "12 Mar 2026, 12:00 UTC"


@pytest.mark.parametrize("event_kind", ["subscription.not_renew", "subscription.disable"])
def test_cancelled_subscription_paid_boundary_and_community_downgrade(lifecycle_app, event_kind):
    app = lifecycle_app
    client, reference = activation(app)
    premium(client, 200)  # Warm the analytics cache before revocation.
    app.extensions["billing_clock"][0] += timedelta(minutes=1)
    assert post(client, "/billing/paystack/cancel").status_code == 303
    drain(app)
    premium(client, 200)
    details = plan(client)
    assert details["Status"] == "Cancelled"
    assert "Next billing" not in details
    assert signed(client, {"event": event_kind, "data": {
        "domain": "test", "subscription_code": "SUB_synthetic",
    }}).status_code == 200
    drain(app)
    old_ledger = ledger(app)
    end = billing.aware(old_ledger[0][4])
    app.extensions["billing_clock"][0] = end - timedelta(microseconds=1)
    client = reauthenticate(app)
    premium(client, 200)
    app.extensions["billing_clock"][0] = end
    premium(client, 403)  # End-exclusive paid period, even if worker has not run yet.
    assert plan(client)["Plan"] == "Community"
    assert post(client, "/billing/paystack/refresh").status_code == 303
    drain(app)
    assert plan(client)["Status"] == "Expired"
    assert signed(client, charge(reference), pretty=True).status_code == 200
    drain(app)
    premium(client, 403)
    assert ledger(app) == old_ledger
    assert plan(client)["Plan"] == "Community"


def test_uncancel_is_provider_confirmed_and_cannot_create_unpaid_access(lifecycle_app):
    app = lifecycle_app
    client, _ = activation(app)
    assert post(client, "/billing/paystack/cancel").status_code == 303
    drain(app)
    fake, clock = app.extensions["billing_fake"], app.extensions["billing_clock"]
    clock[0] += timedelta(minutes=2)
    fake.sub.update(status="active", updatedAt=clock[0].isoformat())
    assert signed(client, {"event": "subscription.disable", "data": {
        "domain": "test", "subscription_code": "SUB_synthetic",
    }}).status_code == 200
    drain(app)
    assert plan(client)["Renewal"] == "Eligible"
    premium(client, 200)
    clock[0] = billing.aware(ledger(app)[0][4])
    client = reauthenticate(app)
    assert post(client, "/billing/paystack/refresh").status_code == 303
    drain(app)
    premium(client, 403)  # Provider status active is not evidence of another payment.


@pytest.mark.parametrize("mutation", ["disabled", "unverified", "session_revoked", "reversed", "billing_off"])
def test_paid_access_does_not_survive_identity_or_payment_revocation(lifecycle_app, mutation):
    app = lifecycle_app
    client, reference = activation(app)
    premium(client, 200)
    if mutation == "reversed":
        tx = app.extensions["billing_fake"].transactions[reference]
        tx.update(status="reversed")
        assert signed(client, charge(reference)).status_code == 200
        drain(app)
    elif mutation == "billing_off":
        app.config["PAYSTACK_TEST_CHECKOUT_ENABLED"] = False
    else:
        with app.app_context():
            user = db.session.get(User, app.extensions["billing_users"]["customer"])
            if mutation == "disabled":
                user.is_active = False
            elif mutation == "unverified":
                user.email_verified_at = None
            else:
                user.session_token = "revoked-d1-session"
            db.session.commit()
    premium(client, 401 if mutation in {"disabled", "session_revoked"} else 403)


def test_invalid_webhook_bytes_wrong_key_and_malformed_payload(lifecycle_app):
    app = lifecycle_app
    client, reference = checkout(app)
    original = json.dumps(charge(reference)).encode()
    signature = hmac.new(SECRET.encode(), original, hashlib.sha512).hexdigest()
    for raw, sig, status in (
        (original + b" ", signature, 401),
        (original, hmac.new(b"wrong-test-key", original, hashlib.sha512).hexdigest(), 401),
        (b"not json", hmac.new(SECRET.encode(), b"not json", hashlib.sha512).hexdigest(), 400),
        (b"[]", hmac.new(SECRET.encode(), b"[]", hashlib.sha512).hexdigest(), 400),
    ):
        response = client.post(WEBHOOK, data=raw, content_type="application/json",
                               headers={"x-paystack-signature": sig})
        assert response.status_code == status
    with app.app_context():
        assert BillingEvent.query.count() == 0
    premium(client, 403)
    assert client.post(WEBHOOK, data=original, content_type="application/json",
                       headers={"x-paystack-signature": signature.upper()}).status_code == 200
    premium(client, 403)
    drain(app)
    premium(client, 200)


def test_concurrent_http_callbacks_and_semantic_replays_apply_once(lifecycle_app):
    app = lifecycle_app
    _, reference = checkout(app)
    clients = [reauthenticate(app) for _ in range(4)]
    def deliver(index):
        client = clients[index]
        assert client.get(CALLBACK + "?reference=" + reference).status_code == 303
        return signed(client, charge(reference), pretty=bool(index % 2)).json["queued"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(deliver, range(4))) == 2
    def process(_):
        with app.app_context():
            return billing.process_one()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(process, range(8)))
    app.extensions["billing_clock"][0] += timedelta(minutes=6)
    drain(app)
    premium(clients[0], 200)
    assert len(ledger(app)) == 1
    before = ledger(app)
    assert signed(clients[0], charge(reference)).json["queued"] is False
    assert signed(clients[0], charge(reference), pretty=True).json["queued"] is False
    drain(app)
    assert ledger(app) == before
    with app.app_context():
        assert BillingEvent.query.count() == 3  # callback + two distinct signed byte encodings
        assert BillingEvent.query.filter_by(status="processed").count() == 3


def test_query_forgery_cannot_bypass_pending_expired_or_cross_account_access(lifecycle_app):
    app = lifecycle_app
    client, _ = checkout(app)
    for endpoint in (REPORT, EXPORT):
        response = client.get(endpoint + "?user_id=1&plan=pro&preview=true&currency=NGN",
                              headers={"X-Plan": "pro", "X-User-Id": "1", "Cache-Control": "no-cache"})
        assert response.status_code == 403
    assert post(client, "/billing/paystack/refresh").status_code == 303
    drain(app)
    premium(client, 200)
    for endpoint in (REPORT, EXPORT):
        assert client.get(endpoint + WINDOW + "&user_id=1").status_code == 400
        assert client.post(endpoint, json={"role": "pro"}).status_code == 405
    premium(reauthenticate(app, "other"), 403)
    app.extensions["billing_clock"][0] += timedelta(days=29)
    client = reauthenticate(app)
    premium(client, 403)


def test_public_services_preview_and_observations_survive_full_lifecycle(lifecycle_app):
    app = lifecycle_app
    before = energy_rows(app)
    anonymous = app.test_client()
    with app.app_context():
        town = next(node["slug"] for node in hierarchy_nodes() if node["level"] == "town")
    def public():
        for path in ("/", "/states", "/state/lagos", "/state/edo", "/region/north-central",
                     "/research", "/articles", "/methodology", "/sitemap.xml", "/robots.txt",
                     "/api/history?hours=8760&limit=20", "/api/states/lagos?hours=720",
                     "/api/regions/north-central?hours=720"):
            assert anonymous.get(path).status_code == 200, path
        preview = anonymous.get("/api/pro/towns/" + town)
        assert preview.status_code == 200 and preview.json["access"] == "pro_preview"
        assert preview.json["data_grade"] == "planning_estimate"
        assert anonymous.get("/api/geography/town/" + town).status_code == 200
        assert energy_rows(app) == before
    public()
    client, _ = activation(app)
    public()
    assert post(client, "/billing/paystack/cancel").status_code == 303
    drain(app)
    app.extensions["billing_clock"][0] += timedelta(days=29)
    public()
    app.config["PAYSTACK_TEST_CHECKOUT_ENABLED"] = False
    app.config["PREMIUM_GATING_ENABLED"] = False
    assert anonymous.get(REPORT).status_code == 404
    for path in ("/research", "/articles", "/state/lagos", "/api/geography/town/" + town):
        assert anonymous.get(path).status_code == 200
    assert energy_rows(app) == before
    assert app.config["PRO_PREVIEW_ENABLED"] is True
    assert not app.config["LIVE_BILLING_ENABLED"] and not app.config["USD_CHECKOUT_ENABLED"]


def test_test_transport_is_not_a_production_provider_option(tmp_path, monkeypatch):
    for key in ("BILLING_PROVIDER", "PAYSTACK_MOCK_ENABLED", "MOCK_PAYMENTS_ENABLED"):
        monkeypatch.setenv(key, "mock")
    config = type("DisabledProductionBilling", (BillingConfig,), {
        "TESTING": False, "ACCOUNTS_ENABLED": False, "SUBSCRIPTIONS_ENABLED": False,
        "PREMIUM_GATING_ENABLED": False, "PAYSTACK_TEST_CHECKOUT_ENABLED": False,
        "APP_BASE_URL": "https://nigeriapowerdata.com", "PAYSTACK_SECRET_KEY": "",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "disabled.sqlite"),
        "SQLALCHEMY_ENGINE_OPTIONS": {}, "SESSION_COOKIE_SECURE": True,
    })
    app = create_app(config)
    with app.app_context():
        assert type(paystack.provider()) is paystack.Paystack
        with pytest.raises(paystack.BillingError, match="billing_disabled"):
            paystack.provider().verify("synthetic")
        assert not billing.process_one()
        db.drop_all()
    assert app.test_client().post(CHECKOUT).status_code == 404
    assert app.test_client().post(WEBHOOK).status_code == 404
    root = Path(__file__).resolve().parents[1] / "grid_monitor"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            modules = ([item.name for item in node.names] if isinstance(node, ast.Import)
                       else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(name == "tests" or name.startswith("tests.") for name in modules), path


@pytest.mark.parametrize("host", [
    "nigeriapowerdata.com", "www.nigeriapowerdata.com", "nigeria-power-dashboard-1.onrender.com",
])
def test_mock_test_values_cannot_enable_billing_on_production_host(host):
    with pytest.raises(RuntimeError, match="non-production"):
        create_app(type("InvalidProductionBilling", (BillingConfig,), {
            "TESTING": False, "APP_BASE_URL": "https://" + host,
            "PAYSTACK_SANDBOX_ORIGIN": "https://" + host,
        }))


def test_browser_checkout_activation_and_cancelled_expiry(lifecycle_app):
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server

    app = lifecycle_app
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors, unexpected, checkout_redirects = [], [], []
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(service_workers="block")
            def route(request_route):
                url = request_route.request.url
                if url == base + CHECKOUT and request_route.request.method == "POST":
                    # Redirect chains can bypass subsequent route interception.
                    # Fetch only our first hop, assert its real redirect, then show
                    # the fixture locally without any connection to Paystack.
                    response = request_route.fetch(max_redirects=0)
                    assert response.status == 303
                    destination = response.headers["location"]
                    assert destination == "https://checkout.paystack.com/synthetic"
                    checkout_redirects.append(destination)
                    request_route.fulfill(status=200, content_type="text/html",
                                          body="<title>Synthetic checkout</title><h1>Synthetic checkout</h1>")
                elif urlsplit(url).netloc == urlsplit(base).netloc:
                    request_route.continue_()
                else:
                    unexpected.append(url)
                    request_route.abort()
            context.route("**/*", route)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            def login():
                page.goto(base + "/login")
                page.locator("#email").fill("customer@example.com")
                page.locator("#password").fill(PASSWORD)
                page.get_by_role("button", name="Sign in", exact=True).click()
                page.wait_for_url("**/account")
                page.goto(base + "/account/billing")
            login()
            page.get_by_role("button", name="Open NGN test checkout").click()
            page.wait_for_url(base + CHECKOUT)
            assert page.get_by_role("heading", name="Synthetic checkout").is_visible()
            assert len(checkout_redirects) == 1
            with app.app_context():
                reference = BillingAccount.query.one().checkout_reference
            page.goto(base + CALLBACK + "?reference=" + reference)
            assert "Community" in page.locator("dl.account-details").inner_text()
            raw = json.dumps(charge(reference)).encode()
            response = context.request.post(base + WEBHOOK, data=raw, headers={
                "Content-Type": "application/json",
                "x-paystack-signature": hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest(),
            })
            assert response.status == 200
            result = app.test_cli_runner().invoke(args=["billing-worker", "--once"])
            assert result.exit_code == 0, result.output
            page.reload()
            assert "Pro (sandbox)" in page.locator("dl.account-details").inner_text()
            assert context.request.get(base + EXPORT + WINDOW).status == 200
            for width in (1440, 768, 390, 320):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                assert page.get_by_role("button", name="Cancel renewal").is_visible()
            page.get_by_role("button", name="Cancel renewal").click()
            page.wait_for_url("**/account/billing")
            drain(app)
            page.reload()
            assert "Cancelled" in page.locator("dl.account-details").inner_text()
            app.extensions["billing_clock"][0] = billing.aware(ledger(app)[0][4])
            login()
            assert "Community" in page.locator("dl.account-details").inner_text()
            assert context.request.get(base + EXPORT + WINDOW).status == 403
            assert errors == [], errors
            assert unexpected == [], unexpected
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
