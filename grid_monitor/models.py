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
