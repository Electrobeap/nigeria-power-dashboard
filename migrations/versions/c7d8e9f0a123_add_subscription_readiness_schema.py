"""add subscription readiness schema

Revision ID: c7d8e9f0a123
Revises: a91b2c3d4e5f6
Create Date: 2026-10-11 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a123"
down_revision = "a91b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index(batch_op.f("ix_users_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_users_role"), ["role"], unique=False)

    op.create_table(
        "subscription_plan_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=True),
        sa.Column("interval", sa.String(length=16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("checkout_enabled", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_code", "currency", "version", name="uq_subscription_plan_price_version"),
    )
    with op.batch_alter_table("subscription_plan_prices", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_subscription_plan_prices_currency"), ["currency"], unique=False)
        batch_op.create_index(batch_op.f("ix_subscription_plan_prices_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_subscription_plan_prices_plan_code"), ["plan_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_subscription_plan_prices_version"), ["version"], unique=False)

    op.create_table(
        "payment_provider_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("provider_plan_code", sa.String(length=255), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=True),
        sa.Column("interval", sa.String(length=16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "plan_code", "currency", "environment", name="uq_payment_provider_plan_currency_environment"),
    )
    with op.batch_alter_table("payment_provider_plans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_payment_provider_plans_currency"), ["currency"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_provider_plans_environment"), ["environment"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_provider_plans_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_provider_plans_plan_code"), ["plan_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_provider_plans_provider"), ["provider"], unique=False)

    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("billing_amount_minor", sa.Integer(), nullable=False),
        sa.Column("price_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_customer_reference", sa.String(length=255), nullable=True),
        sa.Column("provider_subscription_reference", sa.String(length=255), nullable=True),
        sa.Column("provider_plan_reference", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subscription_reference", name="uq_subscription_provider_reference"),
    )
    with op.batch_alter_table("user_subscriptions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_subscriptions_currency"), ["currency"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_subscriptions_current_period_end"), ["current_period_end"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_subscriptions_plan_code"), ["plan_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_subscriptions_provider_customer_reference"), ["provider_customer_reference"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_subscriptions_provider_subscription_reference"), ["provider_subscription_reference"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_subscriptions_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_subscriptions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=255), nullable=True),
        sa.Column("provider_customer_reference", sa.String(length=255), nullable=True),
        sa.Column("provider_subscription_reference", sa.String(length=255), nullable=True),
        sa.Column("payment_channel", sa.String(length=64), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fees_minor", sa.Integer(), nullable=True),
        sa.Column("settlement_amount_minor", sa.Integer(), nullable=True),
        sa.Column("settlement_currency", sa.String(length=3), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["user_subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_reference", name="uq_payment_provider_reference"),
    )
    with op.batch_alter_table("payment_transactions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_payment_transactions_currency"), ["currency"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_paid_at"), ["paid_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_provider"), ["provider"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_provider_customer_reference"), ["provider_customer_reference"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_provider_reference"), ["provider_reference"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_provider_subscription_reference"), ["provider_subscription_reference"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_provider_transaction_id"), ["provider_transaction_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_subscription_id"), ["subscription_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_transactions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_invoice_reference", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_due_minor", sa.Integer(), nullable=False),
        sa.Column("amount_paid_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["user_subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_invoice_reference", name="uq_invoice_provider_reference"),
    )
    with op.batch_alter_table("billing_invoices", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_billing_invoices_currency"), ["currency"], unique=False)
        batch_op.create_index(batch_op.f("ix_billing_invoices_provider"), ["provider"], unique=False)
        batch_op.create_index(batch_op.f("ix_billing_invoices_provider_invoice_reference"), ["provider_invoice_reference"], unique=False)
        batch_op.create_index(batch_op.f("ix_billing_invoices_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_billing_invoices_subscription_id"), ["subscription_id"], unique=False)

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("event_reference", sa.String(length=255), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_reference", name="uq_webhook_provider_event_reference"),
    )
    with op.batch_alter_table("payment_webhook_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_payment_webhook_events_event_reference"), ["event_reference"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_webhook_events_event_type"), ["event_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_webhook_events_processing_status"), ["processing_status"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_webhook_events_provider"), ["provider"], unique=False)
        batch_op.create_index(batch_op.f("ix_payment_webhook_events_received_at"), ["received_at"], unique=False)


def downgrade():
    with op.batch_alter_table("payment_webhook_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_received_at"))
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_provider"))
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_processing_status"))
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_event_type"))
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_event_reference"))
    op.drop_table("payment_webhook_events")

    with op.batch_alter_table("billing_invoices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_invoices_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_billing_invoices_status"))
        batch_op.drop_index(batch_op.f("ix_billing_invoices_provider_invoice_reference"))
        batch_op.drop_index(batch_op.f("ix_billing_invoices_provider"))
        batch_op.drop_index(batch_op.f("ix_billing_invoices_currency"))
    op.drop_table("billing_invoices")

    with op.batch_alter_table("payment_transactions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_transactions_user_id"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_status"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_provider_transaction_id"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_provider_subscription_reference"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_provider_reference"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_provider_customer_reference"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_provider"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_paid_at"))
        batch_op.drop_index(batch_op.f("ix_payment_transactions_currency"))
    op.drop_table("payment_transactions")

    with op.batch_alter_table("user_subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_subscriptions_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_subscriptions_status"))
        batch_op.drop_index(batch_op.f("ix_user_subscriptions_provider_subscription_reference"))
        batch_op.drop_index(batch_op.f("ix_user_subscriptions_provider_customer_reference"))
        batch_op.drop_index(batch_op.f("ix_user_subscriptions_plan_code"))
        batch_op.drop_index(batch_op.f("ix_user_subscriptions_current_period_end"))
        batch_op.drop_index(batch_op.f("ix_user_subscriptions_currency"))
    op.drop_table("user_subscriptions")

    with op.batch_alter_table("payment_provider_plans", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_provider_plans_provider"))
        batch_op.drop_index(batch_op.f("ix_payment_provider_plans_plan_code"))
        batch_op.drop_index(batch_op.f("ix_payment_provider_plans_is_active"))
        batch_op.drop_index(batch_op.f("ix_payment_provider_plans_environment"))
        batch_op.drop_index(batch_op.f("ix_payment_provider_plans_currency"))
    op.drop_table("payment_provider_plans")

    with op.batch_alter_table("subscription_plan_prices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscription_plan_prices_version"))
        batch_op.drop_index(batch_op.f("ix_subscription_plan_prices_plan_code"))
        batch_op.drop_index(batch_op.f("ix_subscription_plan_prices_is_active"))
        batch_op.drop_index(batch_op.f("ix_subscription_plan_prices_currency"))
    op.drop_table("subscription_plan_prices")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_role"))
        batch_op.drop_index(batch_op.f("ix_users_is_active"))
        batch_op.drop_index(batch_op.f("ix_users_email"))
    op.drop_table("users")
