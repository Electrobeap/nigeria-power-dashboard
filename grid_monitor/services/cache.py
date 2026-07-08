import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable

from flask import current_app, has_app_context


_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
_lock = Lock()


def _max_entries() -> int:
    if has_app_context():
        return current_app.config.get("ANALYTICS_CACHE_MAX_ENTRIES", 32)
    return 32


def _prune(now: float, ttl_seconds: int | None = None) -> None:
    if ttl_seconds is not None:
        for key in list(_cache):
            if now - _cache[key]["stored_at"] > ttl_seconds:
                _cache.pop(key, None)
    while len(_cache) > _max_entries():
        _cache.popitem(last=False)


def get_cached(key: str, ttl_seconds: int, loader: Callable[[], Any]) -> Any:
    now = time.time()
    with _lock:
        _prune(now, ttl_seconds)
        entry = _cache.get(key)
        if entry and now - entry["stored_at"] <= ttl_seconds:
            _cache.move_to_end(key)
            return entry["value"]

    value = loader()
    with _lock:
        _cache[key] = {"stored_at": now, "value": value}
        _cache.move_to_end(key)
        _prune(time.time())
    return value


def clear_cache(prefix: str | None = None) -> None:
    with _lock:
        if prefix is None:
            _cache.clear()
            return
        for key in list(_cache):
            if key.startswith(prefix):
                _cache.pop(key, None)


def cache_status() -> dict[str, Any]:
    now = time.time()
    with _lock:
        prefix_counts: dict[str, int] = {}
        for key in _cache:
            prefix = key.split(":", 1)[0]
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
        return {
            "entries": len(_cache),
            "max_entries": _max_entries(),
            "prefix_counts": prefix_counts,
            "oldest_age_seconds": (
                round(now - next(iter(_cache.values()))["stored_at"])
                if _cache
                else None
            ),
        }
