from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint

from grid_monitor.extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GridSnapshot(db.Model):
    __tablename__ = "grid_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    reading_timestamp = db.Column(db.DateTime(timezone=True), nullable=False, unique=True, index=True)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    as_at_time = db.Column(db.String(16))
    total_generation_mw = db.Column(db.Float, nullable=False, index=True)
    reporting_gencos = db.Column(db.Integer)
    source = db.Column(db.String(255))
    source_url = db.Column(db.String(500))
    daily_json = db.Column(db.JSON, nullable=False, default=dict)
    disco_as_at = db.Column(db.String(255))
    total_load_allocation_mw = db.Column(db.Float)
    raw_payload_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    genco_data = db.relationship(
        "GencoData",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="desc(GencoData.generation_mw)",
    )
    disco_data = db.relationship(
        "DiscoData",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="desc(DiscoData.load_allocation_mw)",
    )
    analytics_snapshots = db.relationship(
        "AnalyticsSnapshot",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    distribution_snapshots = db.relationship(
        "DistributionIntelligenceSnapshot",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class GencoData(db.Model):
    __tablename__ = "genco_data"
    __table_args__ = (UniqueConstraint("snapshot_id", "plant", name="uq_genco_snapshot_plant"),)

    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("grid_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    plant = db.Column(db.String(255), nullable=False, index=True)
    generation_mw = db.Column(db.Float)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    snapshot = db.relationship("GridSnapshot", back_populates="genco_data")


class DiscoData(db.Model):
    __tablename__ = "disco_data"
    __table_args__ = (UniqueConstraint("snapshot_id", "company", name="uq_disco_snapshot_company"),)

    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("grid_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    company = db.Column(db.String(255), nullable=False, index=True)
    load_allocation_mw = db.Column(db.Float)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    snapshot = db.relationship("GridSnapshot", back_populates="disco_data")


class AnalyticsSnapshot(db.Model):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "window_hours", name="uq_analytics_snapshot_window"),
    )

    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("grid_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    window_hours = db.Column(db.Integer, nullable=False, index=True)
    trend_json = db.Column(db.JSON, nullable=False, default=dict)
    volatility_json = db.Column(db.JSON, nullable=False, default=dict)
    health_json = db.Column(db.JSON, nullable=False, default=dict)
    stability_json = db.Column(db.JSON, nullable=False, default=dict)
    outage_json = db.Column(db.JSON, nullable=False, default=dict)
    concentration_json = db.Column(db.JSON, nullable=False, default=dict)
    top_gencos_json = db.Column(db.JSON, nullable=False, default=list)
    summary_json = db.Column(db.JSON, nullable=False, default=dict)

    snapshot = db.relationship("GridSnapshot", back_populates="analytics_snapshots")


class DistributionIntelligenceSnapshot(db.Model):
    __tablename__ = "distribution_intelligence_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "window_hours", name="uq_distribution_snapshot_window"),
    )

    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("grid_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    window_hours = db.Column(db.Integer, nullable=False, index=True)
    region_count = db.Column(db.Integer, nullable=False, default=0)
    weighted_utilization_percent = db.Column(db.Float)
    overload_warning_classification = db.Column(db.String(32), index=True)
    regional_risk_json = db.Column(db.JSON, nullable=False, default=list)
    transformer_trend_json = db.Column(db.JSON, nullable=False, default=list)
    settlement_growth_json = db.Column(db.JSON, nullable=False, default=dict)
    utilization_json = db.Column(db.JSON, nullable=False, default=dict)
    summary_json = db.Column(db.JSON, nullable=False, default=dict)

    snapshot = db.relationship("GridSnapshot", back_populates="distribution_snapshots")
