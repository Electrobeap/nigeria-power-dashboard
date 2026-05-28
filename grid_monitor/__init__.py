import atexit
<<<<<<< HEAD
import sys

from flask import Flask
=======
import logging
import sys

from flask import Flask
from flask_migrate import stamp, upgrade
>>>>>>> b9a999e (Disable Scheduler for Render deployment)

from grid_monitor.config import Config
from grid_monitor.extensions import db, migrate
from grid_monitor.routes.api import api_bp
from grid_monitor.routes.web import web_bp
from grid_monitor.services.scheduler import start_scheduler, stop_scheduler
<<<<<<< HEAD
from grid_monitor.services.storage import init_database
from grid_monitor.utils.logging import configure_logging, log_event


=======
from grid_monitor.services.storage import _ensure_sqlite_parent, init_database
from grid_monitor.utils.logging import configure_logging, log_event


_migrations_ran = False


def run_startup_migrations() -> None:
    global _migrations_ran

    if _migrations_ran:
        return

    try:
        _ensure_sqlite_parent()
        upgrade()
        _migrations_ran = True
        log_event("database_migrations_applied")
    except Exception as exc:
        message = str(exc).lower()
        existing_schema_error = any(
            marker in message
            for marker in (
                "already exists",
                "duplicate table",
                "duplicate column",
                "duplicate key",
            )
        )
        if existing_schema_error:
            stamp(revision="head")
            _migrations_ran = True
            log_event(
                "database_migrations_stamped_existing_schema",
                level=logging.WARNING,
                error=str(exc),
            )
            return
        log_event("database_migrations_failed", level=logging.ERROR, error=str(exc))
        raise


>>>>>>> b9a999e (Disable Scheduler for Render deployment)
def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db)

<<<<<<< HEAD
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        init_database()

    is_flask_db_command = "db" in sys.argv
    if app.config["HISTORY_CAPTURE_ENABLED"] and not is_flask_db_command:
=======
    is_flask_db_command = "db" in sys.argv
    with app.app_context():
        if app.config["RUN_MIGRATIONS_ON_STARTUP"] and not is_flask_db_command:
            run_startup_migrations()
        init_database()

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    if False:
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
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
