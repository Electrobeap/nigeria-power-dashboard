"""add distribution intelligence schema

Revision ID: a91b2c3d4e5f6
Revises: 766d4d39b615
Create Date: 2026-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a91b2c3d4e5f6"
down_revision = "766d4d39b615"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "distribution_intelligence_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_hours", sa.Integer(), nullable=False),
        sa.Column("region_count", sa.Integer(), nullable=False),
        sa.Column("weighted_utilization_percent", sa.Float(), nullable=True),
        sa.Column("overload_warning_classification", sa.String(length=32), nullable=True),
        sa.Column("regional_risk_json", sa.JSON(), nullable=False),
        sa.Column("transformer_trend_json", sa.JSON(), nullable=False),
        sa.Column("settlement_growth_json", sa.JSON(), nullable=False),
        sa.Column("utilization_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["grid_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "window_hours", name="uq_distribution_snapshot_window"),
    )
    with op.batch_alter_table("distribution_intelligence_snapshots", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_distribution_intelligence_snapshots_calculated_at"),
            ["calculated_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_distribution_intelligence_snapshots_overload_warning_classification"),
            ["overload_warning_classification"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_distribution_intelligence_snapshots_snapshot_id"),
            ["snapshot_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_distribution_intelligence_snapshots_window_hours"),
            ["window_hours"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("distribution_intelligence_snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_distribution_intelligence_snapshots_window_hours"))
        batch_op.drop_index(batch_op.f("ix_distribution_intelligence_snapshots_snapshot_id"))
        batch_op.drop_index(
            batch_op.f("ix_distribution_intelligence_snapshots_overload_warning_classification")
        )
        batch_op.drop_index(batch_op.f("ix_distribution_intelligence_snapshots_calculated_at"))

    op.drop_table("distribution_intelligence_snapshots")
