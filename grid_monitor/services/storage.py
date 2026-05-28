import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from grid_monitor.extensions import db
from grid_monitor.models import (
    AnalyticsSnapshot,
    DiscoData,
    DistributionIntelligenceSnapshot,
    GencoData,
    GridSnapshot,
)
from grid_monitor.services.cache import clear_cache
from grid_monitor.services.validation import validate_live_payload
from grid_monitor.utils.logging import log_event
from grid_monitor.utils.time import source_reading_timestamp, to_iso, utc_now


def _ensure_sqlite_parent() -> None:
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        return
    sqlite_path = Path(uri.replace("sqlite:///", "", 1))
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def init_database() -> None:
    try:
        _ensure_sqlite_parent()
        if current_app.config["AUTO_CREATE_TABLES"]:
            db.create_all()
        log_event(
            "database_initialized",
            database_uri=current_app.config["SAFE_DATABASE_URI"],
            auto_create_tables=current_app.config["AUTO_CREATE_TABLES"],
        )
    except SQLAlchemyError as exc:
        log_event(
            "database_initialization_failed",
            level=logging.ERROR,
            database_uri=current_app.config["SAFE_DATABASE_URI"],
            error=str(exc),
        )
        if current_app.config["REQUIRE_DATABASE_ON_STARTUP"]:
            raise


def save_grid_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    validate_live_payload(payload)
    reading_timestamp = source_reading_timestamp(payload)
    existing = GridSnapshot.query.filter_by(reading_timestamp=reading_timestamp).first()
    if existing:
        return {
            "inserted": False,
            "snapshot_id": existing.id,
            "reading_timestamp": to_iso(existing.reading_timestamp),
        }

    disco_profile = payload.get("disco_profile") or {}
    snapshot = GridSnapshot(
        reading_timestamp=reading_timestamp,
        captured_at=source_reading_timestamp({"fetched_at": payload.get("fetched_at")}),
        as_at_time=payload.get("as_at_time"),
        total_generation_mw=float(payload["total_generation_mw"]),
        reporting_gencos=payload.get("reporting_gencos"),
        source=payload.get("source"),
        source_url=payload.get("source_url"),
        daily_json=payload.get("daily") or {},
        disco_as_at=disco_profile.get("as_at"),
        total_load_allocation_mw=disco_profile.get("total_load_allocation_mw"),
        raw_payload_json=payload,
    )
    snapshot.genco_data = [
        GencoData(plant=row.get("plant"), generation_mw=row.get("generation_mw"))
        for row in payload.get("gencos") or []
        if row.get("plant")
    ]
    snapshot.disco_data = [
        DiscoData(company=row.get("company"), load_allocation_mw=row.get("load_allocation_mw"))
        for row in disco_profile.get("discos") or []
        if row.get("company")
    ]

    try:
        db.session.add(snapshot)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = GridSnapshot.query.filter_by(reading_timestamp=reading_timestamp).first()
        return {
            "inserted": False,
            "snapshot_id": existing.id if existing else None,
            "reading_timestamp": to_iso(reading_timestamp),
        }
    except SQLAlchemyError:
        db.session.rollback()
        log_event("snapshot_save_failed", logging.ERROR, reading_timestamp=to_iso(reading_timestamp))
        raise

    clear_cache("analytics:")
    clear_cache("history:")
    return {
        "inserted": True,
        "snapshot_id": snapshot.id,
        "reading_timestamp": to_iso(snapshot.reading_timestamp),
    }


def save_analytics_snapshot(snapshot_id: int, window_hours: int, analytics: dict[str, Any]) -> dict[str, Any]:
    existing = AnalyticsSnapshot.query.filter_by(
        snapshot_id=snapshot_id,
        window_hours=window_hours,
    ).first()
    record = existing or AnalyticsSnapshot(snapshot_id=snapshot_id, window_hours=window_hours)
    record.trend_json = analytics.get("last_24h_generation_trend") or analytics.get("trend") or {}
    record.volatility_json = analytics.get("generation_volatility") or {}
    record.health_json = analytics.get("grid_health") or {}
    record.stability_json = {
        "supply": analytics.get("supply_stability_score"),
        "rolling_health": analytics.get("rolling_health_score"),
    }
    record.outage_json = analytics.get("outage_detection") or {}
    record.concentration_json = analytics.get("disco_load_concentration") or {}
    record.top_gencos_json = analytics.get("top_performing_gencos") or []
    record.summary_json = analytics

    try:
        db.session.add(record)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log_event(
            "analytics_snapshot_save_failed",
            logging.ERROR,
            snapshot_id=snapshot_id,
            window_hours=window_hours,
        )
        raise

    clear_cache("analytics:")
    clear_cache("history:")
    return {"analytics_snapshot_id": record.id, "window_hours": window_hours}


def save_distribution_snapshot(
    snapshot_id: int,
    window_hours: int,
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    existing = DistributionIntelligenceSnapshot.query.filter_by(
        snapshot_id=snapshot_id,
        window_hours=window_hours,
    ).first()
    summary = intelligence.get("summary") or {}
    utilization = intelligence.get("transformer_utilization") or {}
    record = existing or DistributionIntelligenceSnapshot(
        snapshot_id=snapshot_id,
        window_hours=window_hours,
    )
    record.region_count = summary.get("region_count") or 0
    record.weighted_utilization_percent = utilization.get("weighted_utilization_percent")
    record.overload_warning_classification = summary.get("overload_warning_classification")
    record.regional_risk_json = intelligence.get("regional_risk") or []
    record.transformer_trend_json = intelligence.get("transformer_loading_trend") or []
    record.settlement_growth_json = intelligence.get("settlement_expansion_impact") or {}
    record.utilization_json = utilization
    record.summary_json = intelligence

    try:
        db.session.add(record)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log_event(
            "distribution_snapshot_save_failed",
            logging.ERROR,
            snapshot_id=snapshot_id,
            window_hours=window_hours,
        )
        raise

    clear_cache("distribution:")
    return {"distribution_snapshot_id": record.id, "window_hours": window_hours}


def snapshot_to_payload(snapshot: GridSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.id,
        "reading_timestamp": to_iso(snapshot.reading_timestamp),
        "captured_at": to_iso(snapshot.captured_at),
        "as_at_time": snapshot.as_at_time,
        "total_generation_mw": snapshot.total_generation_mw,
        "reporting_gencos": snapshot.reporting_gencos,
        "daily": snapshot.daily_json or {},
        "gencos": [
            {"plant": row.plant, "generation_mw": row.generation_mw}
            for row in sorted(snapshot.genco_data, key=lambda item: item.generation_mw or 0, reverse=True)
        ],
        "disco_profile": {
            "as_at": snapshot.disco_as_at,
            "discos": [
                {"company": row.company, "load_allocation_mw": row.load_allocation_mw}
                for row in sorted(
                    snapshot.disco_data,
                    key=lambda item: item.load_allocation_mw or 0,
                    reverse=True,
                )
            ],
            "total_load_allocation_mw": snapshot.total_load_allocation_mw,
            "source": "NISO NIGGRID DISCOs Load Profile",
            "source_url": current_app.config["NIGGRID_DISCO_URL"],
            "fetched_at": to_iso(snapshot.captured_at),
        },
        "source": snapshot.source,
        "source_url": snapshot.source_url,
        "fetched_at": to_iso(snapshot.captured_at),
        "stored": True,
    }


def get_latest_snapshot_model() -> GridSnapshot | None:
    return GridSnapshot.query.order_by(GridSnapshot.reading_timestamp.desc()).first()


def get_latest_snapshot() -> dict[str, Any] | None:
    snapshot = get_latest_snapshot_model()
    return snapshot_to_payload(snapshot) if snapshot else None


def get_history_points(hours: float, limit: int) -> list[dict[str, Any]]:
    since = utc_now() - timedelta(hours=hours)
    rows = (
        GridSnapshot.query.filter(GridSnapshot.reading_timestamp >= since)
        .order_by(GridSnapshot.reading_timestamp.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        rows = GridSnapshot.query.order_by(GridSnapshot.reading_timestamp.desc()).limit(limit).all()
    rows = list(reversed(rows))

    return [
        {
            "snapshot_id": row.id,
            "timestamp": to_iso(row.reading_timestamp),
            "captured_at": to_iso(row.captured_at),
            "as_at_time": row.as_at_time,
            "total_generation_mw": float(row.total_generation_mw),
            "reporting_gencos": row.reporting_gencos,
        }
        for row in rows
    ]


def storage_status() -> dict[str, Any]:
    try:
        snapshot_count = GridSnapshot.query.count()
        analytics_count = AnalyticsSnapshot.query.count()
        distribution_count = DistributionIntelligenceSnapshot.query.count()
        latest = get_latest_snapshot_model()
        return {
            "ok": True,
            "database_uri": current_app.config["SAFE_DATABASE_URI"],
            "snapshot_count": snapshot_count,
            "analytics_snapshot_count": analytics_count,
            "distribution_snapshot_count": distribution_count,
            "latest_timestamp": to_iso(latest.reading_timestamp) if latest else None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "database_uri": current_app.config["SAFE_DATABASE_URI"],
            "error": str(exc),
        }
