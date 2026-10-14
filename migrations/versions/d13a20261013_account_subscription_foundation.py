"""Add opt-in accounts and immutable prices; never alter energy tables.

Revision ID: d13a20261013
Revises: a91b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa

revision = "d13a20261013"
down_revision = "a91b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("session_token", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_table("subscription_plan_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_code", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("plan_code", "currency", "version", name="uq_subscription_plan_price_version"),
        sa.CheckConstraint("currency IN ('NGN', 'USD')", name="ck_price_currency"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_price_nonnegative"),
    )
    op.create_table("user_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_code", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("billing_amount_minor", sa.Integer(), nullable=False),
        sa.Column("price_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(50)),
        sa.Column("provider_customer_reference", sa.String(255)),
        sa.Column("provider_subscription_reference", sa.String(255)),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_subscription_reference", name="uq_subscription_provider_reference"),
        sa.CheckConstraint("currency IN ('NGN', 'USD')", name="ck_subscription_currency"),
        sa.CheckConstraint("billing_amount_minor >= 0", name="ck_subscription_nonnegative"),
        sa.CheckConstraint("plan_code IN ('community', 'pro')", name="ck_subscription_plan"),
        sa.CheckConstraint("status IN ('free', 'pending', 'active', 'past_due', 'cancelled', 'expired')", name="ck_subscription_status"),
    )
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
    op.create_index("ix_user_subscriptions_current_period_end", "user_subscriptions", ["current_period_end"])
    op.create_table("account_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("purpose IN ('reset', 'verify')", name="ck_account_token_purpose"),
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_index("ix_account_tokens_expires_at", "account_tokens", ["expires_at"])
    op.create_table("auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"])
    # Deliberately no startup price seed, user seed, energy-table changes, or provider credentials.


def downgrade():
    raise RuntimeError("Non-destructive rollback: disable account flags and roll back application code. Retain account and energy data; review any schema removal separately.")
