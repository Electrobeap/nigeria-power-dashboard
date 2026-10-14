import atexit
import gzip
import logging
import sys

from alembic import command
from flask import Flask, current_app, request, session

from grid_monitor.config import Config
from grid_monitor.extensions import db, migrate
from grid_monitor.routes.billing import billing_bp
from grid_monitor.services.billing import register_billing_commands
from grid_monitor.routes.accounts import accounts_bp
from grid_monitor.routes.premium import premium_bp
from grid_monitor.routes.subscriptions import subscription_bp
from grid_monitor.services.accounts import init_accounts, start_mail_queue, validate_account_schema
from grid_monitor.services.subscriptions import seed_subscription_pricing
from grid_monitor.routes.api import api_bp
from grid_monitor.routes.geography import geo_fast_bp
from grid_monitor.routes.research import research_bp
from grid_monitor.routes.web import web_bp
from grid_monitor.services.indexnow import start_indexnow_startup_notification
from grid_monitor.services.scheduler import start_scheduler, stop_scheduler
from grid_monitor.services.storage import _ensure_sqlite_parent, init_database
from grid_monitor.utils.logging import configure_logging, log_event


_migrations_ran = False
COMPRESSIBLE_MIMETYPES = {
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "application/xml",
    "image/svg+xml",
    "text/css",
    "text/html",
    "text/javascript",
    "text/plain",
    "text/xml",
}


def _alembic_config(app: Flask):
    extension = app.extensions["migrate"]
    return extension.migrate.get_config(extension.directory)


def run_startup_migrations() -> None:
    global _migrations_ran

    if _migrations_ran:
        return

    try:
        _ensure_sqlite_parent()
        command.upgrade(_alembic_config(current_app), "head")
        _migrations_ran = True
        log_event("database_migrations_applied")
    except BaseException as exc:
        if current_app.config["REQUIRE_DATABASE_ON_STARTUP"]:
            log_event("database_migrations_failed", level=logging.ERROR, error=str(exc))
            raise
        log_event("database_migrations_skipped_after_error", level=logging.ERROR, error=str(exc))


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db)
    init_accounts(app)

    is_flask_db_command = "db" in sys.argv
    is_billing_command = any(name in sys.argv for name in ("billing-worker", "billing-retry", "billing-status"))
    start_background_services = not is_flask_db_command and not is_billing_command
    with app.app_context():
        if app.config["RUN_MIGRATIONS_ON_STARTUP"] and not is_flask_db_command:
            run_startup_migrations()
        init_database()
        if not is_flask_db_command:
            validate_account_schema(app)

    app.register_blueprint(accounts_bp)
    app.register_blueprint(billing_bp)
    register_billing_commands(app)
    app.register_blueprint(subscription_bp)
    app.register_blueprint(premium_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(geo_fast_bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    if app.config["HISTORY_CAPTURE_ENABLED"] and start_background_services:
        start_scheduler(app)
    if app.config["INDEXNOW_ENABLED"] and start_background_services:
        start_indexnow_startup_notification(app)

    if start_background_services:
        start_mail_queue(app)

    @app.cli.command("seed-subscription-prices")
    def seed_prices_command():
        """Insert immutable reviewed price versions; never update contracts."""
        seed_subscription_pricing()

    log_event("app_startup", database_uri=app.config["SAFE_DATABASE_URI"])
    atexit.register(stop_scheduler)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    @app.after_request
    def add_production_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.path in {"/favicon.svg", "/robots.txt", "/sitemap.xml"}:
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "public, max-age=300"

        if request.blueprint in {"accounts", "billing"} or request.path.startswith("/api/pro/") or (app.config.get("ACCOUNTS_ENABLED") and session.get("_user_id")):
            response.headers["Cache-Control"] = "private, no-store"
            response.vary.add("Cookie")

        if request.path.startswith("/api/pro/"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            response.headers["Pragma"] = "no-cache"

        accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "").lower()
        should_compress = (
            accepts_gzip
            and request.blueprint not in {"accounts", "billing"}
            and not request.path.startswith("/api/pro/")
            and request.method != "HEAD"
            and "Range" not in request.headers
            and response.status_code < 300
            and not response.headers.get("Content-Encoding")
            and response.mimetype in COMPRESSIBLE_MIMETYPES
        )
        if should_compress:
            response.direct_passthrough = False
            body = response.get_data()
            if len(body) >= 1024:
                compressed = gzip.compress(body, compresslevel=6)
                response.set_data(compressed)
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Content-Length"] = str(len(compressed))
                response.headers.pop("ETag", None)
                vary_header = response.headers.get("Vary")
                if vary_header:
                    vary_values = {value.strip().lower() for value in vary_header.split(",")}
                    if "accept-encoding" not in vary_values:
                        response.headers["Vary"] = f"{vary_header}, Accept-Encoding"
                else:
                    response.headers["Vary"] = "Accept-Encoding"
        return response

    return app
