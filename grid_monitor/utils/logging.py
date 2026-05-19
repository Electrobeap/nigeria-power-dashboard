import json
import logging
from datetime import datetime, timezone
from typing import Any

from flask import current_app, has_app_context


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            payload = record.msg
        else:
            payload = {"message": record.getMessage()}
        payload.setdefault("level", record.levelname)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        payload.setdefault("logger", record.name)
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(app) -> None:
    level = getattr(logging, app.config["LOG_LEVEL"], logging.INFO)
    logging.basicConfig(level=level)
    formatter = JsonFormatter()
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)
    app.logger.setLevel(level)
    logging.getLogger("grid_monitor").setLevel(level)


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    logger = current_app.logger if has_app_context() else logging.getLogger("grid_monitor")
    logger.log(level, {"event": event, **fields})
