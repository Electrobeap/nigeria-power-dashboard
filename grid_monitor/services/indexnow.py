import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from flask import current_app

from grid_monitor.config import DATA_DIR
from grid_monitor.services.site_urls import public_urls
from grid_monitor.utils.logging import log_event
from grid_monitor.utils.time import utc_now_iso


INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def indexnow_key() -> str:
    key = current_app.config["INDEXNOW_KEY"].strip()
    if not INDEXNOW_KEY_PATTERN.fullmatch(key):
        raise ValueError("INDEXNOW_KEY must be 8-128 letters, numbers, or dashes")
    return key


def indexnow_key_file_name() -> str:
    return f"{indexnow_key()}.txt"


def indexnow_key_file_body() -> str:
    return indexnow_key()


def indexnow_key_file_url() -> str:
    return f"{current_app.config['APP_BASE_URL']}/{indexnow_key_file_name()}"


def indexnow_status() -> dict[str, Any]:
    urls = public_urls(current_app.config["APP_BASE_URL"])
    return {
        "enabled": current_app.config["INDEXNOW_ENABLED"],
        "auto_notify_enabled": current_app.config["INDEXNOW_AUTO_NOTIFY_ENABLED"],
        "endpoint": current_app.config["INDEXNOW_ENDPOINT"],
        "key_file": indexnow_key_file_name(),
        "key_file_url": indexnow_key_file_url(),
        "url_count": len(urls),
        "publication_version": current_app.config["INDEXNOW_PUBLICATION_VERSION"],
    }


def _state_file() -> Path:
    return Path(DATA_DIR) / "indexnow_last_submission.json"


def _read_state() -> dict[str, Any]:
    path = _state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict[str, Any]) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def _fingerprint(urls: list[str]) -> str:
    payload = {
        "publication_version": current_app.config["INDEXNOW_PUBLICATION_VERSION"],
        "urls": sorted(urls),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _unique_valid_urls(urls: list[str]) -> list[str]:
    host = urlparse(current_app.config["APP_BASE_URL"]).netloc.lower()
    unique_urls = []
    seen = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != host:
            continue
        if url not in seen:
            unique_urls.append(url)
            seen.add(url)
    return unique_urls[:10000]


def submit_indexnow_urls(
    urls: list[str] | None = None,
    *,
    reason: str = "manual",
    dry_run: bool = False,
) -> dict[str, Any]:
    if not current_app.config["INDEXNOW_ENABLED"]:
        return {"ok": True, "submitted": False, "skipped": True, "reason": "indexnow_disabled"}

    resolved_urls = _unique_valid_urls(urls or public_urls(current_app.config["APP_BASE_URL"]))
    if not resolved_urls:
        return {"ok": False, "submitted": False, "error": "no_valid_urls"}

    payload = {
        "host": urlparse(current_app.config["APP_BASE_URL"]).netloc,
        "key": indexnow_key(),
        "urlList": resolved_urls,
    }
    if dry_run:
        return {
            "ok": True,
            "submitted": False,
            "dry_run": True,
            "reason": reason,
            "endpoint": current_app.config["INDEXNOW_ENDPOINT"],
            "payload": payload,
            "url_count": len(resolved_urls),
        }

    response = requests.post(
        current_app.config["INDEXNOW_ENDPOINT"],
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=current_app.config["INDEXNOW_SUBMIT_TIMEOUT_SECONDS"],
    )
    ok = response.status_code in {200, 202}
    result = {
        "ok": ok,
        "submitted": ok,
        "reason": reason,
        "endpoint": current_app.config["INDEXNOW_ENDPOINT"],
        "status_code": response.status_code,
        "url_count": len(resolved_urls),
        "response_text": response.text[:500],
    }
    log_event(
        "indexnow_submission",
        level=logging.INFO if ok else logging.WARNING,
        **{key: value for key, value in result.items() if key != "response_text"},
    )
    return result


def submit_public_urls_if_due(*, force: bool = False, reason: str = "startup") -> dict[str, Any]:
    urls = public_urls(current_app.config["APP_BASE_URL"])
    fingerprint = _fingerprint(urls)
    state = _read_state()
    now = time.time()
    min_interval = current_app.config["INDEXNOW_STARTUP_MIN_INTERVAL_SECONDS"]
    submitted_recently = now - float(state.get("submitted_at_epoch") or 0) < min_interval
    unchanged = state.get("fingerprint") == fingerprint

    if not force and unchanged and submitted_recently:
        return {
            "ok": True,
            "submitted": False,
            "skipped": True,
            "reason": "unchanged_recent_submission",
            "url_count": len(urls),
        }

    result = submit_indexnow_urls(urls, reason=reason)
    if result.get("ok") and result.get("submitted"):
        _write_state(
            {
                "fingerprint": fingerprint,
                "submitted_at": utc_now_iso(),
                "submitted_at_epoch": now,
                "url_count": len(urls),
                "reason": reason,
            }
        )
    return result


def start_indexnow_startup_notification(app) -> None:
    if not app.config["INDEXNOW_AUTO_NOTIFY_ENABLED"]:
        return

    def _submit() -> None:
        with app.app_context():
            try:
                result = submit_public_urls_if_due(reason="startup")
                log_event("indexnow_startup_notification_complete", **result)
            except Exception as exc:
                log_event(
                    "indexnow_startup_notification_failed",
                    level=logging.WARNING,
                    error=str(exc),
                )

    thread = threading.Thread(target=_submit, name="indexnow-startup", daemon=True)
    thread.start()
