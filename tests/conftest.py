import os

import pytest
from sqlalchemy.engine import make_url

from grid_monitor import create_app
from grid_monitor.config import Config
from grid_monitor.extensions import db

from tests.billing_support import billing_app as billing_app, billing_epoch as billing_epoch


def pytest_configure(config):
    """Reject accidental production DB use before any destructive test fixture."""
    uri = os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL")
    if not uri:
        return
    try:
        url = make_url(uri)
        safe = (url.get_backend_name() == "postgresql"
                and url.host in {"localhost", "127.0.0.1", "::1"}
                and url.username == "npd_test" and url.database == "npd_test"
                and not url.query)
    except Exception:
        safe = False
    if not safe:
        raise pytest.UsageError(
            "Tests destroy their database. SUBSCRIPTION_TEST_DATABASE_URL must use "
            "local PostgreSQL with username/database npd_test and no URL options."
        )



class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ.get("SUBSCRIPTION_TEST_DATABASE_URL") or "sqlite:///:memory:"
    SAFE_DATABASE_URI = "isolated-test-database"
    SQLALCHEMY_ENGINE_OPTIONS = ({"connect_args": {"check_same_thread": False}}
                                if SQLALCHEMY_DATABASE_URI.startswith("sqlite:") else {})
    RUN_MIGRATIONS_ON_STARTUP = False
    REQUIRE_DATABASE_ON_STARTUP = False
    AUTO_CREATE_TABLES = True
    HISTORY_CAPTURE_ENABLED = False
    WEB_SCHEDULER_ENABLED = False
    HISTORY_CAPTURE_ON_STARTUP = False
    INDEXNOW_ENABLED = False
    INDEXNOW_AUTO_NOTIFY_ENABLED = False
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
