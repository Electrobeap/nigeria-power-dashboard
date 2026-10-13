"""Account/pricing foundation. Synthetic users only; no external payment calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
import os
import re
from threading import Thread

from alembic import command
from bs4 import BeautifulSoup
import pytest
from sqlalchemy import inspect, select, text

from grid_monitor import _alembic_config, create_app
from grid_monitor.config import Config
from grid_monitor.extensions import db
from grid_monitor.models import GridSnapshot, GencoData, DiscoData
from grid_monitor.services.accounts import consume_token, issue_token, throttle
from grid_monitor.services.entitlements import access_decision, entitlement_snapshot
from grid_monitor.services.subscriptions import seed_subscription_pricing
from grid_monitor.subscription_models import (
    AccountToken, AuthRateLimit, SubscriptionPlanPrice, User, UserSubscription, utc_now,
)

PASSWORD = "A unique synthetic passphrase 2026"
OTHER_PASSWORD = "Another synthetic passphrase 2026"


class AccountConfig(Config):
    TESTING = True
    SECRET_KEY = "synthetic-test-only-secret-with-more-than-32-characters"
    ACCOUNTS_ENABLED = True
    AUTH_EMAIL_ENABLED = True
    AUTH_EMAIL_VERIFICATION_REQUIRED = False
    AUTH_MAIL_FROM = "test@example.com"
    AUTH_MAIL_SYNCHRONOUS = True
    SESSION_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL") or "sqlite:///:memory:"
    SAFE_DATABASE_URI = "isolated-test-database"
    SQLALCHEMY_ENGINE_OPTIONS = ({"connect_args": {"check_same_thread": False}}
                                if SQLALCHEMY_DATABASE_URI.startswith("sqlite:") else {})
    RUN_MIGRATIONS_ON_STARTUP = False
    AUTO_CREATE_TABLES = True
    HISTORY_CAPTURE_ENABLED = False
    WEB_SCHEDULER_ENABLED = False
    INDEXNOW_ENABLED = False
    INDEXNOW_AUTO_NOTIFY_ENABLED = False


@pytest.fixture()
def account_app():
    app = create_app(AccountConfig)
    messages = []
    app.config["AUTH_MAIL_SENDER"] = messages.append
    app.extensions["test_mail"] = messages
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    queue = app.extensions.get("account_mail_queue")
    if queue:
        queue[0].shutdown(wait=True)


@pytest.fixture()
def customer(account_app):
    with account_app.app_context():
        user = User(email="customer@example.com", email_verified_at=utc_now())
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.flush()
        db.session.add(UserSubscription(user_id=user.id, plan_code="community", status="free",
                                       currency="NGN", billing_amount_minor=0))
        db.session.commit()
        return user.id


def csrf_token(client, path="/login", **kwargs):
    response = client.get(path, **kwargs)
    assert response.status_code == 200
    return BeautifulSoup(response.data, "html.parser").select_one('input[name="csrf_token"]')["value"]


def post_form(client, path, values, **kwargs):
    values = dict(values, csrf_token=csrf_token(client, path, **kwargs))
    return client.post(path, data=values, **kwargs)


def sign_in(client, **kwargs):
    return post_form(client, "/login", {"email": "customer@example.com", "password": PASSWORD}, **kwargs)


def test_default_flags_pricing_and_no_billing(client):
    assert Config.ACCOUNTS_ENABLED is False
    assert Config.SUBSCRIPTIONS_ENABLED is False
    assert Config.PREMIUM_GATING_ENABLED is False
    assert Config.PRO_PREVIEW_ENABLED is True
    for currency, amount in (("NGN", 750000), ("USD", 900)):
        response = client.get("/api/subscriptions/pricing?currency=" + currency)
        assert response.status_code == 200
        payload = response.json
        assert payload["plans"][0]["amount_minor"] == 0
        assert payload["plans"][1]["amount_minor"] == amount
        assert all(not item["checkout_enabled"] for item in payload["plans"])
        assert all(item["formatted_price"] == "Contact Sales" for item in payload["plans"][2:])
        assert payload["usd_checkout_enabled"] is False
        page = BeautifulSoup(client.get("/pricing?currency=" + currency).data, "html.parser")
        assert len(page.select('link[rel="canonical"]')) == 1
        assert page.select_one('link[rel="canonical"]')["href"].endswith("/pricing")
        assert len(page.select('script[type="application/ld+json"]')) == 1
        assert len(page.select(".pricing-card")) == 4
        assert page.select_one(f'a[aria-current="true"][href$="currency={currency}"]')
    assert client.get("/pricing?currency=BTC").status_code == 400
    for path in ("/login", "/register", "/account", "/forgot-password", "/reset-password", "/verify-email"):
        assert client.get(path).status_code == 404
    assert client.post("/api/billing/paystack/initialize", json={"amount": 1, "currency": "USD"}).status_code == 404
    assert client.post("/api/billing/paystack/webhook", json={}).status_code == 404


def test_csrf_and_registration_is_always_community(account_app):
    client = account_app.test_client()
    values = {"email": "New.User@example.com", "password": PASSWORD, "accept_terms": "yes",
              "currency": "USD", "role": "admin", "plan_code": "pro", "status": "active"}
    assert client.post("/register", data=values).status_code == 400
    assert client.post("/register", data={**values, "csrf_token": "forged"}).status_code == 400
    first = post_form(client, "/register", values)
    assert first.status_code == 200
    second = post_form(client, "/register", {**values, "email": "new.user@EXAMPLE.com"})
    assert second.status_code == 200
    assert first.data == second.data
    with account_app.app_context():
        assert User.query.count() == 1
        user = User.query.one()
        assert user.email == "new.user@example.com"
        assert user.check_password(PASSWORD)
        assert user.password_hash.startswith("scrypt:32768:8:3$")
        assert PASSWORD not in user.password_hash
        sub = UserSubscription.query.one()
        assert (sub.plan_code, sub.status, sub.billing_amount_minor, sub.currency) == ("community", "free", 0, "USD")
        assert sub.provider is None
        assert not user.email_verified_at
    assert PASSWORD.encode() not in first.data


@pytest.mark.parametrize("change", [
    {"password": "short"}, {"password": "a" * 129}, {"email": "not-an-email"},
    {"currency": "EUR"}, {"accept_terms": "no"},
])
def test_registration_input_validation(account_app, change):
    response = post_form(account_app.test_client(), "/register",
                         {"email": "new@example.com", "password": PASSWORD, "currency": "NGN",
                          "accept_terms": "yes", **change})
    assert response.status_code == 400
    with account_app.app_context():
        assert User.query.count() == 0


def test_login_account_isolation_headers_and_logout_replay(account_app, customer):
    client = account_app.test_client()
    assert client.get("/account").status_code == 302
    assert sign_in(client).status_code == 303
    response = client.get("/account?user_id=999&plan_code=pro", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert b"customer@example.com" in response.data
    assert "private" in response.headers["Cache-Control"] and "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "Content-Encoding" not in response.headers
    assert b"googletagmanager" not in response.data and b"clarity.ms" not in response.data
    cookie = client.get_cookie("session").value
    assert client.get("/logout").status_code == 405
    token = BeautifulSoup(response.data, "html.parser").select_one('input[name="csrf_token"]')["value"]
    assert client.post("/logout", data={}).status_code == 400
    assert client.post("/logout", data={"csrf_token": token}).status_code == 303
    replay = account_app.test_client()
    replay.set_cookie("session", cookie)
    assert replay.get("/account").status_code == 302
    assert client.get("/account").status_code == 302


def test_secure_cookie_and_no_open_redirect(account_app, customer):
    account_app.config["SESSION_COOKIE_SECURE"] = True
    client = account_app.test_client()
    token = csrf_token(client, "/login", base_url="https://localhost")
    response = client.post("/login?next=https://evil.example", base_url="https://localhost",
        headers={"Referer": "https://localhost/login"},
        data={"email": "customer@example.com", "password": PASSWORD, "csrf_token": token})
    assert response.status_code == 303 and response.headers["Location"] == "/account"
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


@pytest.mark.parametrize("email", ["customer@example.com", "unknown@example.com"])
def test_login_throttling_and_generic_errors(account_app, customer, email):
    client = account_app.test_client()
    for _ in range(8):
        response = post_form(client, "/login", {"email": email, "password": "incorrect"})
        assert response.status_code == 401
        assert b"Unable to sign in." in response.data
    response = post_form(client, "/login", {"email": email, "password": PASSWORD})
    assert response.status_code == 429 and response.headers["Retry-After"] == "900"
    with account_app.app_context():
        rows = AuthRateLimit.query.all()
        assert rows and all(len(row.key) == 64 and "@" not in row.key for row in rows)


def test_account_session_has_absolute_expiry(account_app, customer):
    client = account_app.test_client()
    assert sign_in(client).status_code == 303
    with client.session_transaction() as state:
        state["account_issued_at"] = utc_now().timestamp() - 9 * 3600
    assert client.get("/account").status_code == 302


def test_recovery_privacy_single_use_and_session_invalidation(account_app, customer):
    client = account_app.test_client()
    assert sign_in(client).status_code == 303
    old_cookie = client.get_cookie("session").value
    known = post_form(client, "/forgot-password", {"email": "customer@example.com"})
    unknown = post_form(client, "/forgot-password", {"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 200 and known.data == unknown.data
    message = account_app.extensions["test_mail"][0].get_content()
    token = re.search(r"#token=([A-Za-z0-9_-]{43})", message)[1]
    assert "https://nigeriapowerdata.com/reset-password#token=" in message
    assert token.encode() not in known.data
    with account_app.app_context():
        saved = AccountToken.query.one()
        assert saved.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert saved.token_hash != token
    assert post_form(client, "/verify-email", {"token": token}).status_code == 400
    response = post_form(client, "/reset-password", {"token": token, "password": OTHER_PASSWORD})
    assert response.status_code == 200
    assert post_form(client, "/reset-password", {"token": token, "password": PASSWORD}).status_code == 400
    replay = account_app.test_client()
    replay.set_cookie("session", old_cookie)
    assert replay.get("/account").status_code == 302
    with account_app.app_context():
        assert db.session.get(User, customer).check_password(OTHER_PASSWORD)


def test_expired_replaced_tokens_and_inactive_users(account_app, customer):
    with account_app.app_context():
        user = db.session.get(User, customer)
        first = issue_token(user, "reset")
        second = issue_token(user, "reset")
        assert not consume_token(first, "reset", OTHER_PASSWORD)
        record = AccountToken.query.one()
        record.expires_at = utc_now() - timedelta(seconds=1)
        db.session.commit()
        assert not consume_token(second, "reset", OTHER_PASSWORD)
        user.is_active = False
        db.session.commit()
        third = issue_token(user, "reset")
        assert not consume_token(third, "reset", OTHER_PASSWORD)
        assert user.check_password(PASSWORD)


def test_required_email_verification(account_app, customer):
    account_app.config["AUTH_EMAIL_VERIFICATION_REQUIRED"] = True
    with account_app.app_context():
        user = db.session.get(User, customer)
        user.email_verified_at = None
        db.session.commit()
        token = issue_token(user, "verify")
    client = account_app.test_client()
    assert sign_in(client).status_code == 401
    assert post_form(client, "/verify-email", {"token": token}).status_code == 200
    assert post_form(client, "/verify-email", {"token": token}).status_code == 400
    assert sign_in(client).status_code == 303


def test_mail_disabled_and_delivery_failure_do_not_expose_tokens(account_app, customer, caplog):
    client = account_app.test_client()
    def fail(message):
        raise RuntimeError("SECRET-SMTP-DETAILS customer@example.com")
    account_app.config["AUTH_MAIL_SENDER"] = fail
    response = post_form(client, "/forgot-password", {"email": "customer@example.com"})
    assert response.status_code == 200
    assert "SECRET-SMTP-DETAILS" not in caplog.text
    assert "customer@example.com" not in caplog.text
    account_app.config["AUTH_EMAIL_ENABLED"] = False
    assert client.get("/forgot-password").status_code == 503


def test_server_prices_are_immutable_and_never_exchange_converted(account_app):
    with account_app.app_context():
        assert SubscriptionPlanPrice.query.count() == 0
        seed_subscription_pricing()
        seed_subscription_pricing()
        assert SubscriptionPlanPrice.query.count() == 4
        ngn = SubscriptionPlanPrice.query.filter_by(plan_code="pro", currency="NGN").one()
        usd = SubscriptionPlanPrice.query.filter_by(plan_code="pro", currency="USD").one()
        assert (ngn.amount_minor, usd.amount_minor) == (750000, 900)
        ngn.amount_minor = 1
        db.session.commit()
        with pytest.raises(ValueError, match="new version"):
            seed_subscription_pricing()
        assert ngn.amount_minor == 1


def test_entitlement_expiry_waiver_and_unknown_features(account_app, customer):
    with account_app.app_context():
        user = db.session.get(User, customer)
        assert entitlement_snapshot(user)["plan_code"] == "community"
        assert access_decision("town_intelligence")["reason"] == "pro_preview"
        assert access_decision("town_intelligence")["data_grade"] == "planning_estimate"
        assert not access_decision("invented_feature")["allowed"]
        account_app.config.update(SUBSCRIPTIONS_ENABLED=True, PREMIUM_GATING_ENABLED=True)
        for feature in ("national_dashboard", "regional_dashboard", "state_dashboard", "public_history", "research"):
            assert access_decision(feature)["allowed"]
        assert not access_decision("extended_history", user)["allowed"]
        assert access_decision("town_intelligence", user)["allowed"]
        account_app.config["PRO_PREVIEW_ENABLED"] = False
        assert not access_decision("town_intelligence", user)["allowed"]
        subscription = UserSubscription(user_id=customer, plan_code="pro", status="active", currency="NGN",
            billing_amount_minor=750000, current_period_start=utc_now() - timedelta(days=1),
            current_period_end=utc_now() + timedelta(days=29))
        db.session.add(subscription)
        db.session.commit()
        for feature in ("extended_history", "advanced_exports", "town_intelligence"):
            assert access_decision(feature, user)["allowed"]
        subscription.status = "cancelled"
        db.session.commit()
        assert entitlement_snapshot(user)["premium_access_active"]
        subscription.current_period_end = utc_now() - timedelta(seconds=1)
        db.session.commit()
        assert not entitlement_snapshot(user)["premium_access_active"]
        subscription.current_period_end = None
        db.session.commit()
        assert not entitlement_snapshot(user)["premium_access_active"]


@pytest.mark.parametrize("overrides", [
    {"SECRET_KEY": "weak"},
    {"AUTH_EMAIL_VERIFICATION_REQUIRED": True, "AUTH_EMAIL_ENABLED": False},
    {"APP_BASE_URL": "https://attacker:password@example.org"},
    {"APP_BASE_URL": "http://untrusted.example"},
    {"PREMIUM_GATING_ENABLED": True},
    {"PAYSTACK_TEST_CHECKOUT_ENABLED": True},
    {"USD_CHECKOUT_ENABLED": True},
    {"LIVE_BILLING_ENABLED": True},
])
def test_unsafe_startup_configuration_rejected(overrides):
    config = type("UnsafeConfig", (AccountConfig,), overrides)
    with pytest.raises(RuntimeError):
        create_app(config)


def test_additive_migration_preserves_observations_and_schema(tmp_path):
    uri = os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL") or "sqlite:///" + str(tmp_path / "migration.sqlite")
    config = type("MigrationConfig", (AccountConfig,), {
        "ACCOUNTS_ENABLED": False, "AUTH_EMAIL_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": uri, "AUTO_CREATE_TABLES": False,
    })
    app = create_app(config)
    with app.app_context():
        db.drop_all()
        db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()
        command.upgrade(_alembic_config(app), "a91b2c3d4e5f6")
        snapshot = GridSnapshot(reading_timestamp=utc_now(), captured_at=utc_now(),
            total_generation_mw=4321.5, source="synthetic-preservation-test", daily_json={},
            raw_payload_json={"sentinel": "unchanged"})
        db.session.add(snapshot)
        db.session.flush()
        db.session.add_all([
            GencoData(snapshot_id=snapshot.id, plant="Synthetic plant", generation_mw=123),
            DiscoData(snapshot_id=snapshot.id, company="Synthetic distributor", load_allocation_mw=45),
        ])
        db.session.commit()
        energy_tables = ["grid_snapshots", "genco_data", "disco_data", "analytics_snapshots",
                         "distribution_intelligence_snapshots"]
        before = {name: db.session.execute(text("SELECT * FROM " + name)).mappings().all() for name in energy_tables}
        before = {name: [dict(row) for row in rows] for name, rows in before.items()}
        db.session.rollback()
        command.upgrade(_alembic_config(app), "head")
        command.upgrade(_alembic_config(app), "head")
        after = {name: [dict(row) for row in db.session.execute(text("SELECT * FROM " + name)).mappings()] for name in energy_tables}
        assert before == after
        for model in (User, UserSubscription, SubscriptionPlanPrice, AccountToken, AuthRateLimit):
            actual = {col["name"] for col in inspect(db.engine).get_columns(model.__tablename__)}
            assert actual == set(model.__table__.columns.keys())
        assert db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() == "d13a20261013"
        db.session.rollback()
        with pytest.raises(RuntimeError, match="Non-destructive rollback"):
            command.downgrade(_alembic_config(app), "a91b2c3d4e5f6")
        assert db.session.execute(text("SELECT total_generation_mw FROM grid_snapshots")).scalar() == 4321.5
        db.session.rollback()
        db.drop_all()
        db.session.execute(text("DROP TABLE alembic_version"))
        db.session.commit()


@pytest.mark.skipif(not os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL"), reason="PostgreSQL concurrency job")
def test_atomic_throttle_and_reset_under_concurrency(account_app, customer):
    def attempt(_):
        with account_app.test_request_context("/login", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            return throttle("concurrency", "customer@example.com")
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(12)))
    assert sum(results) == 8
    with account_app.app_context():
        token = issue_token(db.session.get(User, customer), "reset")
    def consume(_):
        with account_app.app_context():
            return consume_token(token, "reset", OTHER_PASSWORD)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, range(2)))
    assert sum(results) == 1


def test_account_and_pricing_browser_layouts(account_app, customer):
    from playwright.sync_api import sync_playwright
    server = __import__("werkzeug.serving", fromlist=["make_server"]).make_server("127.0.0.1", 0, account_app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/")
                       else route.fulfill(status=200, body="", content_type="application/javascript"))
            for width in (1440, 768, 390, 320):
                page.set_viewport_size({"width": width, "height": 1000})
                for path in ("/pricing", "/pricing?currency=USD", "/register", "/login", "/forgot-password", "/reset-password"):
                    response = page.goto(base + path, wait_until="networkidle")
                    assert response.status == 200
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, path)
                page.goto(base + "/reset-password#token=" + "x" * 43, wait_until="networkidle")
                assert page.locator("#account-token").input_value() == "x" * 43
                assert page.evaluate("location.hash") == ""
            page.goto(base + "/login", wait_until="networkidle")
            page.locator("#email").fill("customer@example.com")
            page.locator("#password").fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.wait_for_url("**/account")
            assert page.get_by_role("heading", name="Your account", exact=True).is_visible()
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_startup_migration_failure_never_stamps_head(app, monkeypatch):
    import grid_monitor
    calls = []
    def broken(*args, **kwargs):
        raise RuntimeError("table already exists")
    monkeypatch.setattr(grid_monitor, "_migrations_ran", False)
    monkeypatch.setattr(grid_monitor.command, "upgrade", broken)
    monkeypatch.setattr(grid_monitor.command, "stamp", lambda *a, **k: calls.append("stamped"))
    with app.app_context():
        grid_monitor.run_startup_migrations()
    assert calls == []
    assert grid_monitor._migrations_ran is False


def test_production_accounts_require_verified_migration(account_app):
    from grid_monitor.services.accounts import validate_account_schema
    account_app.testing = False
    with account_app.app_context():
        with pytest.raises(RuntimeError, match="schema verification"):
            validate_account_schema(account_app)
