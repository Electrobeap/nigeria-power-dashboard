"""Bounded daily analysis of stored observations. No scraping, ORM graphs or writes."""
from datetime import date, datetime, time, timedelta, timezone
import math
import re
from statistics import pstdev

from flask import current_app
from sqlalchemy import and_, case, func, select

from grid_monitor.extensions import db
from grid_monitor.models import GridSnapshot
from grid_monitor.services.cache import get_cached
from grid_monitor.subscription_models import utc_now

MAX_RANGE_DAYS = 1827
CSV_FIELDS = ("date", "stored_readings", "valid_readings", "excluded_readings",
              "mean_generation_mw", "minimum_generation_mw", "maximum_generation_mw",
              "daily_range_mw", "change_from_previous_day_mw", "rolling_7_day_mean_mw",
              "calendar_day_elapsed")


class PremiumQueryError(ValueError):
    pass


def validate_query(args, allowed):
    if set(args) - set(allowed) or any(len(args.getlist(key)) != 1 for key in args):
        raise PremiumQueryError("Unknown or repeated query parameters.")


def parse_window(args):
    validate_query(args, {"start", "end"})
    today = utc_now().date()
    if not args:
        return today - timedelta(days=30), today
    if set(args) != {"start", "end"}:
        raise PremiumQueryError("Supply both start and end as UTC dates.")
    try:
        values = [args[key] for key in ("start", "end")]
        if not all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value, flags=re.ASCII) for value in values):
            raise ValueError()
        start, end = (date.fromisoformat(value) for value in values)
    except (ValueError, TypeError):
        raise PremiumQueryError("Use valid YYYY-MM-DD dates.") from None
    if not 1 <= (end - start).days <= MAX_RANGE_DAYS or end > today + timedelta(days=1):
        raise PremiumQueryError("Range must be 1-1827 days, with no future dates.")
    return start, end


def _number(value):
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 4)


def _daily_analysis(start, end):
    start_at = datetime.combine(start, time.min, timezone.utc)
    end_at = datetime.combine(end, time.min, timezone.utc)
    timestamp = GridSnapshot.reading_timestamp
    bucket = func.date(func.timezone("UTC", timestamp)) if db.engine.dialect.name == "postgresql" else func.date(timestamp)
    generation = GridSnapshot.total_generation_mw
    valid = and_(generation >= 0, generation < float("inf"))
    value = case((valid, generation), else_=None)
    rows = db.session.execute(select(
        bucket.label("day"), func.count(GridSnapshot.id).label("stored"),
        func.count(value).label("valid"), func.avg(value).label("mean"),
        func.min(value).label("low"), func.max(value).label("high"),
        func.min(case((valid, timestamp), else_=None)).label("first"),
        func.max(case((valid, timestamp), else_=None)).label("last"),
    ).where(timestamp >= start_at, timestamp < end_at)
      .group_by(bucket).order_by(bucket)).mappings().all()
    indexed = {str(row["day"]): row for row in rows}
    today = utc_now().date()
    daily = []
    unrounded_means = []
    for offset in range((end - start).days):
        day = start + timedelta(days=offset)
        row = indexed.get(day.isoformat())
        mean = float(row["mean"]) if row and row["mean"] is not None else None
        if mean is not None and not math.isfinite(mean):
            mean = None
        low = _number(row["low"]) if row else None
        high = _number(row["high"]) if row else None
        previous = unrounded_means[-1] if unrounded_means else None
        unrounded_means.append(mean)
        window = unrounded_means[-7:]
        rolling = sum(window) / 7 if len(window) == 7 and all(item is not None for item in window) else None
        daily.append({
            "date": day.isoformat(), "stored_readings": int(row["stored"]) if row else 0,
            "valid_readings": int(row["valid"]) if row else 0,
            "excluded_readings": int(row["stored"] - row["valid"]) if row else 0,
            "mean_generation_mw": _number(mean), "minimum_generation_mw": low, "maximum_generation_mw": high,
            "daily_range_mw": _number(high - low) if high is not None and low is not None else None,
            "change_from_previous_day_mw": _number(mean - previous) if mean is not None and previous is not None else None,
            "rolling_7_day_mean_mw": _number(rolling), "calendar_day_elapsed": day < today,
        })
    sources = db.session.execute(select(GridSnapshot.source, GridSnapshot.source_url).where(
        timestamp >= start_at, timestamp < end_at).distinct()
        .order_by(GridSnapshot.source, GridSnapshot.source_url).limit(51)).all()
    observed_means = [item for item in unrounded_means if item is not None]
    firsts = [row["first"] for row in rows if row["first"]]
    lasts = [row["last"] for row in rows if row["last"]]
    def iso(value):
        if not value:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    return {
        "schema_version": 1, "calculated_at": utc_now().isoformat(),
        "window": {"start": start.isoformat(), "end_exclusive": end.isoformat(), "timezone": "UTC"},
        "coverage": {
            "requested_days": len(daily), "days_with_valid_readings": len(observed_means),
            "missing_days": len(daily) - len(observed_means),
            "stored_readings": sum(item["stored_readings"] for item in daily),
            "valid_readings": sum(item["valid_readings"] for item in daily),
            "excluded_readings": sum(item["excluded_readings"] for item in daily),
            "first_observation": iso(min(firsts)) if firsts else None,
            "last_observation": iso(max(lasts)) if lasts else None,
        },
        "statistics": {
            "standard_deviation_of_daily_means_mw": _number(pstdev(observed_means)) if len(observed_means) >= 2 else None,
            "peak_observed_generation_mw": max((item["maximum_generation_mw"] for item in daily if item["maximum_generation_mw"] is not None), default=None),
            "lowest_observed_generation_mw": min((item["minimum_generation_mw"] for item in daily if item["minimum_generation_mw"] is not None), default=None),
        },
        "methodology": {
            "data_grade": "stored_source_observations",
            "aggregation": "Arithmetic mean of valid sampled generation readings per UTC day; not time-weighted energy.",
            "rolling_average": "Equal-weight mean of seven consecutive daily means; null if any day has no valid reading.",
            "variability": "Population standard deviation of observed daily means; not intraday frequency stability or an outage count.",
            "quality": "Negative, null and non-finite readings are excluded, counted and never modified in storage.",
            "limitations": "Missing days are not zero generation. Sampling gaps do not prove grid outages or household supply availability. Source readings are not independently verified.",
            "sources": [{"name": name, "url": url} for name, url in sources[:50]],
            "sources_truncated": len(sources) > 50,
        },
        "daily": daily,
    }


def generation_analysis(start, end):
    # Called only after route authorization. Cache contains no account-specific data.
    key = f"premium:{id(current_app._get_current_object())}:daily-v1:{start}:{end}"
    # Match the shared cache TTL so premium requests cannot prematurely prune public reports.
    return get_cached(key, current_app.config["ANALYTICS_CACHE_TTL_SECONDS"],
                      lambda: _daily_analysis(start, end))
