import atexit
import sys

from flask import Flask

from grid_monitor.config import Config
from grid_monitor.extensions import db, migrate
from grid_monitor.routes.api import api_bp
from grid_monitor.routes.web import web_bp
from grid_monitor.services.scheduler import start_scheduler, stop_scheduler
from grid_monitor.services.storage import init_database
from grid_monitor.utils.logging import configure_logging, log_event


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        init_database()

    is_flask_db_command = "db" in sys.argv
    if app.config["HISTORY_CAPTURE_ENABLED"] and not is_flask_db_command:
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
