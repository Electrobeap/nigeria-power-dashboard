"""Stage B security and data contracts. Isolated test databases and synthetic data only."""
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
import os

from bs4 import BeautifulSoup
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from grid_monitor import create_app
from grid_monitor.config import Config
from grid_monitor.extensions import db
from grid_monitor.models import GridSnapshot
from grid_monitor.services.cache import clear_cache
from grid_monitor.services.entitlements import access_decision, require_pro
from grid_monitor.services.geographic_hierarchy import hierarchy_nodes
from grid_monitor.subscription_models import User, UserSubscription, utc_now

PASSWORD = "Synthetic premium security passphrase"
WINDOW = "?start=2024-01-01&end=2024-01-11"
REPORT = "/api/pro/generation-analysis"
EXPORT = "/api/pro/exports/generation.csv"


class PremiumConfig(Config):
    TESTING = True
    SECRET_KEY = "synthetic-premium-test-only-secret-with-at-least-32-characters"
    SQLALCHEMY_DATABASE_URI = os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL") or "sqlite:///:memory:"
    SAFE_DATABASE_URI = "isolated-premium-test-database"
    SQLALCHEMY_ENGINE_OPTIONS = ({"connect_args": {"check_same_thread": False}}
                                if SQLALCHEMY_DATABASE_URI.startswith("sqlite:") else {})
    ACCOUNTS_ENABLED = True
    SUBSCRIPTIONS_ENABLED = True
    PREMIUM_GATING_ENABLED = True
    PRO_PREVIEW_ENABLED = True
    AUTH_EMAIL_ENABLED = False
    AUTH_EMAIL_VERIFICATION_REQUIRED = False
    SESSION_COOKIE_SECURE = False
    RUN_MIGRATIONS_ON_STARTUP = False
    AUTO_CREATE_TABLES = True
    HISTORY_CAPTURE_ENABLED = False
    WEB_SCHEDULER_ENABLED = False
    INDEXNOW_ENABLED = False
    INDEXNOW_AUTO_NOTIFY_ENABLED = False


@pytest.fixture()
def premium_app():
    clear_cache()
    app = create_app(PremiumConfig)
    with app.app_context():
        template = User(email="template@example.com")
        template.set_password(PASSWORD)
        now = utc_now()
        identities = {}
        roles = ("community", "pro", "expired", "cancelled", "pending", "future",
                 "unverified", "disabled", "missing_end", "past_due", "usd")
        for role in roles:
            user = User(email=role + "@example.com", password_hash=template.password_hash,
                        email_verified_at=None if role == "unverified" else now,
                        is_active=role != "disabled")
            db.session.add(user)
            db.session.flush()
            identities[role] = user.id
            db.session.add(UserSubscription(
                user_id=user.id, plan_code="community" if role == "community" else "pro",
                status={"community": "free", "expired": "expired", "cancelled": "cancelled",
                        "pending": "pending", "past_due": "past_due"}.get(role, "active"),
                currency="USD" if role == "usd" else "NGN",
                billing_amount_minor=0 if role == "community" else 900 if role == "usd" else 750000,
                current_period_start=now + timedelta(days=1) if role == "future" else now - timedelta(days=1),
                current_period_end=None if role == "missing_end" else now - timedelta(seconds=1) if role == "expired" else now + timedelta(days=29),
            ))
        db.session.commit()
        app.extensions["test_identities"] = identities
    yield app
    clear_cache()
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def observations(premium_app):
    with premium_app.app_context():
        for day in range(10):
            if day == 4:
                continue
            for hour, addition in ((0, 0), (12, 200)):
                stamp = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=day, hours=hour)
                db.session.add(GridSnapshot(
                    reading_timestamp=stamp, captured_at=stamp, total_generation_mw=1000 + 100 * day + addition,
                    source="=HYPERLINK(synthetic)", source_url="https://example.com/synthetic",
                    raw_payload_json={"sentinel": "never-select-or-change"}, daily_json={},
                ))
        for day, value in ((1, -10), (2, float("inf"))):
            stamp = datetime(2024, 1, 1, 18, tzinfo=timezone.utc) + timedelta(days=day)
            db.session.add(GridSnapshot(reading_timestamp=stamp, captured_at=stamp,
                total_generation_mw=value, source="synthetic-invalid", daily_json={}))
        db.session.commit()


def login(client, role="pro"):
    page = client.get("/login")
    token = BeautifulSoup(page.data, "html.parser").select_one('input[name="csrf_token"]')["value"]
    return client.post("/login", data={"email": role + "@example.com", "password": PASSWORD, "csrf_token": token})


def private(response):
    assert "private" in response.headers["Cache-Control"]
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert "Cookie" in response.headers["Vary"]
    assert not response.headers.get("Access-Control-Allow-Origin")


@pytest.mark.parametrize("flag", ["ACCOUNTS_ENABLED", "SUBSCRIPTIONS_ENABLED", "PREMIUM_GATING_ENABLED"])
def test_unapproved_services_are_unavailable(premium_app, flag, monkeypatch):
    premium_app.config[flag] = False
    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled endpoints must never read analytics.")
    monkeypatch.setattr("grid_monitor.routes.premium.generation_analysis", forbidden)
    for path in (REPORT, EXPORT):
        response = premium_app.test_client().get(path)
        assert response.status_code == 404
        assert response.json["code"] == "feature_unavailable"
        private(response)


@pytest.mark.parametrize("role,status", [
    (None, 401), ("community", 403), ("expired", 403), ("pending", 403),
    ("future", 403), ("missing_end", 403), ("past_due", 403), ("unverified", 403),
])
@pytest.mark.parametrize("path", [REPORT, EXPORT])
def test_denied_requests_never_reach_data_or_cache(premium_app, role, status, path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unauthorized request reached loader/cache.")
    monkeypatch.setattr("grid_monitor.routes.premium.generation_analysis", forbidden)
    client = premium_app.test_client()
    if role:
        assert login(client, role).status_code == 303
    response = client.get(path + WINDOW, headers={"Accept": "text/csv", "X-Plan": "pro", "X-User-Id": "1"})
    assert response.status_code == status
    assert response.json["ok"] is False
    private(response)
    assert client.head(path + WINDOW).status_code == status


@pytest.mark.parametrize("role", ["pro", "cancelled", "usd"])
def test_verified_paid_through_accounts_can_access_both_capabilities(premium_app, observations, role):
    client = premium_app.test_client()
    assert login(client, role).status_code == 303
    response = client.get(REPORT + WINDOW)
    assert response.status_code == 200
    assert response.json["data"]["coverage"]["stored_readings"] == 20
    private(response)
    response = client.get(EXPORT + WINDOW, headers={"Accept-Encoding": "gzip", "Range": "bytes=0-200"})
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "Content-Encoding" not in response.headers
    private(response)


@pytest.mark.parametrize("suffix", [
    "?start=2024-01-01", "?end=2024-01-11", "?start=&end=2024-01-11",
    "?start=2024-01-01&start=2024-01-02&end=2024-01-11",
    "?start=2024-01-01&end=2024-01-11&end=2024-01-12",
    "?start=2024-1-1&end=2024-01-11", "?start=2024-02-30&end=2024-03-01",
    "?start=NaN&end=Infinity", "?start=2024-01-11&end=2024-01-01",
    "?start=2024-01-01&end=2024-01-01", "?start=2000-01-01&end=2024-01-01",
    "?start=9999-01-01&end=9999-01-02", "?hours=876000", "?limit=-1",
    "?user_id=1", "?plan=pro", "?format=csv", "?currency=NGN",
])
def test_query_manipulation_rejected_after_auth(premium_app, suffix, monkeypatch):
    client = premium_app.test_client()
    assert login(client).status_code == 303
    monkeypatch.setattr("grid_monitor.routes.premium.generation_analysis",
                        lambda *a: pytest.fail("Invalid query reached cache."))
    for path in (REPORT, EXPORT):
        response = client.get(path + suffix)
        assert response.status_code == 400
        assert response.json["code"] == "invalid_query"
        private(response)


def test_no_method_or_parameter_authorization_bypass(premium_app):
    client = premium_app.test_client()
    assert client.get(REPORT + "?user_id=1&plan=pro&preview=true").status_code == 401
    assert client.get(EXPORT + "?status=active&paid_through=9999-01-01").status_code == 401
    for path in (REPORT, EXPORT):
        assert client.post(path, json={"user_id": 1, "role": "pro"}).status_code == 405
        assert client.get(path + "?start=" + "1" * 1100).status_code == 400
        assert client.get(path, data="body").status_code == 400
        assert client.get(path + ".json").status_code == 404


@pytest.mark.parametrize("mutation", ["expired", "past_due", "pending", "disabled", "unverified", "session_revoked"])
def test_warm_cache_cannot_outlive_identity_or_subscription(premium_app, observations, mutation):
    client = premium_app.test_client()
    assert login(client).status_code == 303
    assert client.get(REPORT + WINDOW).status_code == 200
    with premium_app.app_context():
        user = db.session.get(User, premium_app.extensions["test_identities"]["pro"])
        sub = UserSubscription.query.filter_by(user_id=user.id).one()
        if mutation == "expired":
            sub.current_period_end = utc_now() - timedelta(seconds=1)
        elif mutation in {"past_due", "pending"}:
            sub.status = mutation
        elif mutation == "disabled":
            user.is_active = False
        elif mutation == "unverified":
            user.email_verified_at = None
        else:
            user.session_token = "revoked-session-identifier"
        db.session.commit()
    for path in (REPORT, EXPORT):
        assert client.get(path + WINDOW).status_code in (401, 403)
    other = premium_app.test_client()
    assert login(other, "community").status_code == 303
    assert other.get(REPORT + WINDOW).status_code == 403
    assert premium_app.test_client().get(REPORT + WINDOW).status_code == 401


def test_analysis_correctness_csv_and_no_energy_writes(premium_app, observations):
    client = premium_app.test_client()
    assert login(client).status_code == 303
    with premium_app.app_context():
        before = list(db.session.execute(select(GridSnapshot.id, GridSnapshot.total_generation_mw, GridSnapshot.raw_payload_json)))
    report = client.get(REPORT + WINDOW).json["data"]
    assert len(report["daily"]) == 10
    assert report["coverage"]["valid_readings"] == 18
    assert report["coverage"]["excluded_readings"] == 2
    assert report["coverage"]["missing_days"] == 1
    first, second = report["daily"][:2]
    assert first["mean_generation_mw"] == 1100
    assert first["minimum_generation_mw"] == 1000
    assert first["maximum_generation_mw"] == 1200
    assert first["daily_range_mw"] == 200
    assert second["change_from_previous_day_mw"] == 100
    assert report["daily"][4]["mean_generation_mw"] is None
    assert report["daily"][5]["change_from_previous_day_mw"] is None
    assert all(row["rolling_7_day_mean_mw"] is None for row in report["daily"])
    assert report["statistics"]["peak_observed_generation_mw"] == 2100
    assert report["statistics"]["lowest_observed_generation_mw"] == 1000
    assert report["methodology"]["data_grade"] == "stored_source_observations"
    export = client.get(EXPORT + WINDOW)
    rows = list(csv.DictReader(StringIO(export.get_data(as_text=True))))
    assert len(rows) == 10 and float(rows[0]["mean_generation_mw"]) == 1100
    assert rows[4]["mean_generation_mw"] == ""
    assert "HYPERLINK" not in export.get_data(as_text=True)
    assert export.headers["X-Window-End-Exclusive"] == "2024-01-11"
    with premium_app.app_context():
        assert before == list(db.session.execute(select(GridSnapshot.id, GridSnapshot.total_generation_mw, GridSnapshot.raw_payload_json)))


def test_daily_window_boundaries_and_complete_rolling_average(premium_app):
    with premium_app.app_context():
        for day in range(9):
            stamp = datetime(2024, 2, 1, tzinfo=timezone.utc) + timedelta(days=day)
            db.session.add(GridSnapshot(reading_timestamp=stamp, captured_at=stamp,
                total_generation_mw=100 * (day + 1), daily_json={}))
        db.session.commit()
    client = premium_app.test_client()
    login(client)
    data = client.get(REPORT + "?start=2024-02-01&end=2024-02-09").json["data"]
    assert data["coverage"]["stored_readings"] == 8
    assert data["daily"][5]["rolling_7_day_mean_mw"] is None
    assert data["daily"][6]["rolling_7_day_mean_mw"] == 400
    assert data["daily"][7]["rolling_7_day_mean_mw"] == 500


def test_query_projection_cache_and_bounded_output(premium_app, observations):
    statements = []
    with premium_app.app_context():
        engine = db.engine
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(engine, "before_cursor_execute", capture)
    try:
        client = premium_app.test_client()
        login(client)
        response = client.get(REPORT + WINDOW)
        assert response.status_code == 200
        energy = [item for item in statements if "grid_snapshots" in item]
        assert len(energy) == 2
        assert all("raw_payload_json" not in item and "daily_json" not in item for item in energy)
        assert not any("genco_data" in item or "disco_data" in item for item in statements)
        statements.clear()
        assert client.get(EXPORT + WINDOW).status_code == 200
        assert not any("grid_snapshots" in item for item in statements)
        assert any("user_subscriptions" in item for item in statements)
        response = client.get(REPORT + "?start=2019-01-01&end=2024-01-01")
        assert response.status_code == 200 and len(response.json["data"]["daily"]) <= 1827
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_empty_data_is_explicit_not_fabricated(premium_app):
    client = premium_app.test_client()
    login(client)
    response = client.get(REPORT + WINDOW)
    assert response.status_code == 200
    data = response.json["data"]
    assert data["coverage"]["stored_readings"] == 0
    assert data["coverage"]["first_observation"] is None
    assert data["statistics"]["standard_deviation_of_daily_means_mw"] is None
    assert all(row["mean_generation_mw"] is None for row in data["daily"])


def test_authorization_and_data_fail_closed(premium_app, monkeypatch, caplog):
    client = premium_app.test_client()
    login(client)
    def failed(*args, **kwargs):
        raise OperationalError("SECRET QUERY", {}, Exception("SECRET DATABASE"))
    with monkeypatch.context() as scoped:
        scoped.setattr("grid_monitor.services.entitlements.active_subscription", failed)
        response = client.get(REPORT)
        assert response.status_code == 503 and response.json["code"] == "authorization_unavailable"
    monkeypatch.setattr("grid_monitor.routes.premium.generation_analysis", failed)
    response = client.get(EXPORT)
    assert response.status_code == 503 and response.json["code"] == "data_unavailable"
    assert "SECRET" not in caplog.text and b"SECRET" not in response.data
    private(response)


def test_preview_waiver_and_legacy_town_remain_public(premium_app):
    with premium_app.app_context():
        town = next(node for node in hierarchy_nodes() if node["level"] == "town")
    path = "/api/pro/towns/" + town["slug"]
    legacy = "/api/geography/town/" + town["slug"]
    client = premium_app.test_client()
    response = client.get(path)
    assert response.status_code == 200
    assert response.json["access"] == "pro_preview"
    assert response.json["data_grade"] == "planning_estimate"
    assert "dataset_path" not in response.json["data"]["data_lineage"]
    private(response)
    assert client.get(legacy).status_code == 200
    premium_app.config["PRO_PREVIEW_ENABLED"] = False
    assert client.get(path).status_code == 401
    assert client.get(legacy).status_code == 200
    login(client, "community")
    assert client.get(path).status_code == 403
    other = premium_app.test_client()
    login(other)
    assert other.get(path).json["access"] == "pro"
    assert other.get(path + "?preview=true").status_code == 400
    assert other.get("/api/pro/towns/not-a-real-town").status_code == 404


def test_unknown_capability_fails_closed(premium_app):
    with premium_app.app_context():
        assert not access_decision("invented")["allowed"]
    with pytest.raises(ValueError):
        require_pro("invented")


def test_public_routes_and_existing_ranges_are_not_gated(premium_app, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Existing public routes must not invoke premium authorization.")
    monkeypatch.setattr("grid_monitor.services.entitlements.active_subscription", forbidden)
    client = premium_app.test_client()
    for path in ("/", "/states", "/state/lagos", "/state/edo", "/region/north-central",
                 "/research", "/articles", "/methodology", "/sitemap.xml", "/robots.txt",
                 "/api/history?hours=8760&limit=20", "/api/generation?hours=8760&limit=20",
                 "/api/analytics?hours=8760&limit=20", "/api/states/lagos?hours=720",
                 "/api/regions/north-central?hours=720", "/api/geography/map"):
        assert client.get(path).status_code == 200, path
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/api/pro/" not in sitemap
    assert client.get("/api/history?hours=8760").json["hours"] == 8760
    assert not premium_app.config["HISTORY_CAPTURE_ENABLED"]
    assert not premium_app.config["PAYSTACK_TEST_CHECKOUT_ENABLED"]
    assert not premium_app.config["LIVE_BILLING_ENABLED"]
    assert not premium_app.config["USD_CHECKOUT_ENABLED"]


def test_premium_cache_does_not_shorten_public_analytics_ttl(premium_app, monkeypatch):
    from datetime import date
    from grid_monitor.services import cache, premium_analytics
    clock = [1000.0]
    monkeypatch.setattr(cache.time, "time", lambda: clock[0])
    with premium_app.app_context():
        public = {"sentinel": "public-geography"}
        assert cache.get_cached("geography:stage-b-regression", 120, lambda: public) == public
        clock[0] += 60
        monkeypatch.setattr(premium_analytics, "_daily_analysis", lambda *a: {"daily": []})
        premium_analytics.generation_analysis(date(2024, 1, 1), date(2024, 1, 2))
        assert cache.get_cached("geography:stage-b-regression", 120,
                                lambda: pytest.fail("Premium request evicted unexpired public cache.")) == public
