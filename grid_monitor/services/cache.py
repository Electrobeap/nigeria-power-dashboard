import time
from threading import Lock
from typing import Any, Callable


_cache: dict[str, dict[str, Any]] = {}
_lock = Lock()


def get_cached(key: str, ttl_seconds: int, loader: Callable[[], Any]) -> Any:
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if entry and now - entry["stored_at"] <= ttl_seconds:
            return entry["value"]

    value = loader()
    with _lock:
        _cache[key] = {"stored_at": now, "value": value}
    return value


def clear_cache(prefix: str | None = None) -> None:
    with _lock:
        if prefix is None:
            _cache.clear()
            return
        for key in list(_cache):
            if key.startswith(prefix):
                _cache.pop(key, None)
