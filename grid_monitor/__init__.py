import atexit
import logging
import sys

from alembic import command
from flask import Flask, current_app

from grid_monitor.config import Config
from grid_monitor.extensions import db, migrate
from grid_monitor.routes.api import api_bp
from grid_monitor.routes.web import web_bp
from grid_monitor.services.scheduler import start_scheduler, stop_scheduler
from grid_monitor.services.storage import _ensure_sqlite_parent, init_database
from grid_monitor.utils.logging import configure_logging, log_event


_migrations_ran = False


def _alembic_config(app: Flask):
    extension = app.extensions["migrate"]
    return extension.migrate.get_config(extension.directory)


def _is_recoverable_migration_error(error: BaseException) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "already exists",
            "can't locate revision",
            "cannot locate revision",
            "not a valid head",
            "duplicate table",
            "duplicate column",
            "duplicate key",
        )
    )


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
        if _is_recoverable_migration_error(exc):
            command.stamp(_alembic_config(current_app), "head", purge=True)
            _migrations_ran = True
            log_event(
                "database_migrations_stamped_recoverable_state",
                level=logging.WARNING,
                error=str(exc),
            )
            return
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

    is_flask_db_command = "db" in sys.argv
    with app.app_context():
        if app.config["RUN_MIGRATIONS_ON_STARTUP"] and not is_flask_db_command:
            run_startup_migrations()
        init_database()

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    if (
        app.config["WEB_SCHEDULER_ENABLED"]
        and app.config["HISTORY_CAPTURE_ENABLED"]
        and not is_flask_db_command
    ):
        start_scheduler(app)

    log_event("app_startup", database_uri=app.config["SAFE_DATABASE_URI"])
    atexit.register(stop_scheduler)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    @app.after_request
    def add_production_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app
