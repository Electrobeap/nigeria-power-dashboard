"""Add sandbox billing audit tables; never alter account or energy observations.

Revision ID: e14c20261014
Revises: d13a20261013
"""
from alembic import op
import sqlalchemy as sa

revision = "e14c20261014"
down_revision = "d13a20261013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("billing_accounts",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("subscription_id", sa.Integer, sa.ForeignKey("user_subscriptions.id"), nullable=False, unique=True),
        sa.Column("checkout_reference", sa.String(100), nullable=False, unique=True),
        sa.Column("plan_reference", sa.String(100), nullable=False),
        sa.Column("checkout_url", sa.String(512)),
        sa.Column("checkout_status", sa.String(24), nullable=False),
        sa.Column("provider_status", sa.String(24), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True)),
        sa.Column("next_payment_at", sa.DateTime(timezone=True)),
        sa.Column("renewal_enabled", sa.Boolean, nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("billing_payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subscription_id", sa.Integer, sa.ForeignKey("user_subscriptions.id"), nullable=False),
        sa.Column("transaction_id", sa.String(32), nullable=False, unique=True),
        sa.Column("reference", sa.String(100), nullable=False, unique=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("period_start", sa.DateTime(timezone=True)),
        sa.Column("period_end", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("currency = 'NGN'", name="ck_billing_payment_ngn"),
        sa.CheckConstraint("amount_minor = 750000", name="ck_billing_payment_amount"),
        sa.CheckConstraint("status IN ('success', 'failed', 'reversed')", name="ck_billing_payment_status"),
        sa.CheckConstraint("period_end IS NULL OR period_end > period_start", name="ck_billing_payment_period"),
    )
    op.create_index("ix_billing_payments_subscription_id", "billing_payments", ["subscription_id"])
    op.create_table("billing_invoices",
        sa.Column("invoice_code", sa.String(100), primary_key=True),
        sa.Column("subscription_id", sa.Integer, sa.ForeignKey("user_subscriptions.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_minor", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payment_reference", sa.String(100)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("period_end > period_start", name="ck_billing_invoice_period"),
        sa.CheckConstraint("amount_minor = 750000", name="ck_billing_invoice_amount"),
    )
    op.create_index("ix_billing_invoices_subscription_id", "billing_invoices", ["subscription_id"])
    op.create_table("billing_events",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("last_error", sa.String(40)),
    )
    op.create_index("ix_billing_events_available_at", "billing_events", ["available_at"])


def downgrade():
    tables = ("billing_events", "billing_invoices", "billing_payments", "billing_accounts")
    connection = op.get_bind()
    for table in tables:
        if connection.execute(sa.text("SELECT COUNT(*) FROM " + table)).scalar():
            raise RuntimeError("Non-destructive rollback: retain billing audit records; disable sandbox flags and roll back code instead.")
    for table in tables:
        op.drop_table(table)
