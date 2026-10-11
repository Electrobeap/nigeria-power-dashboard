import pytest

from grid_monitor import create_app
from grid_monitor.config import Config
from grid_monitor.extensions import db


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SAFE_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}
    RUN_MIGRATIONS_ON_STARTUP = False
    REQUIRE_DATABASE_ON_STARTUP = False
    AUTO_CREATE_TABLES = True
    HISTORY_CAPTURE_ENABLED = False
    WEB_SCHEDULER_ENABLED = False
    HISTORY_CAPTURE_ON_STARTUP = False
    INDEXNOW_ENABLED = False
    INDEXNOW_AUTO_NOTIFY_ENABLED = False
    SUBSCRIPTIONS_ENABLED = False
    SUBSCRIPTION_SEED_PRICING_ENABLED = False
    PAYSTACK_TEST_MODE = True
    PAYSTACK_TEST_CHECKOUT_ENABLED = False
    PAYSTACK_SECRET_KEY = "sk_test_example"
    PAYSTACK_PUBLIC_KEY = "pk_test_example"
    PAYSTACK_PRO_NGN_PLAN_CODE = "PLN_test_pro_ngn"
    USD_CHECKOUT_ENABLED = False
    USD_PRO_PROVIDER_PLAN_CODE = ""
    CONTACT_EMAIL = "hello@nigeriapowerdata.com"
    RESEARCH_EMAIL = "research@nigeriapowerdata.com"
    ADS_EMAIL = "ads@nigeriapowerdata.com"


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def app_context(app):
    with app.app_context():
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()
