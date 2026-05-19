from datetime import datetime, timedelta, timezone
from typing import Any


NIGERIA_TZ = timezone(timedelta(hours=1), "WAT")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ensure_utc(parsed)


def source_reading_timestamp(payload: dict[str, Any]) -> datetime:
    daily = payload.get("daily") or {}
    source_date = daily.get("performance_date")
    source_time = payload.get("as_at_time")
    if source_date and source_time:
        for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
            try:
                parsed = datetime.strptime(f"{source_date} {source_time.strip()}", fmt)
                return parsed.replace(tzinfo=NIGERIA_TZ).astimezone(timezone.utc)
            except ValueError:
                continue

    fetched_at = parse_iso_datetime(payload.get("fetched_at"))
    return fetched_at or utc_now()


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_utc(value).isoformat()
