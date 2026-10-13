"""Account/contract tables only; never relate to or mutate energy observations."""
from datetime import datetime, timezone
import secrets

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from grid_monitor.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


def session_identifier():
    return secrets.token_urlsafe(32)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    session_token = db.Column(db.String(64), nullable=False, unique=True, default=session_identifier)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    email_verified_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_login_at = db.Column(db.DateTime(timezone=True))

    def get_id(self):
        return self.session_token

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt:32768:8:3")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class SubscriptionPlanPrice(db.Model):
    __tablename__ = "subscription_plan_prices"
    __table_args__ = (
        UniqueConstraint("plan_code", "currency", "version", name="uq_subscription_plan_price_version"),
        CheckConstraint("currency IN ('NGN', 'USD')", name="ck_price_currency"),
        CheckConstraint("amount_minor >= 0", name="ck_price_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    plan_code = db.Column(db.String(50), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    amount_minor = db.Column(db.Integer, nullable=False)
    interval = db.Column(db.String(16), nullable=False, default="month")
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class UserSubscription(db.Model):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_reference", name="uq_subscription_provider_reference"),
        CheckConstraint("currency IN ('NGN', 'USD')", name="ck_subscription_currency"),
        CheckConstraint("billing_amount_minor >= 0", name="ck_subscription_nonnegative"),
        CheckConstraint("plan_code IN ('community', 'pro')", name="ck_subscription_plan"),
        CheckConstraint("status IN ('free', 'pending', 'active', 'past_due', 'cancelled', 'expired')",
                        name="ck_subscription_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_code = db.Column(db.String(50), nullable=False, default="community")
    currency = db.Column(db.String(3), nullable=False, default="NGN")
    billing_amount_minor = db.Column(db.Integer, nullable=False, default=0)
    price_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(32), nullable=False, default="free")
    provider = db.Column(db.String(50))
    provider_customer_reference = db.Column(db.String(255))
    provider_subscription_reference = db.Column(db.String(255))
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class AccountToken(db.Model):
    __tablename__ = "account_tokens"
    __table_args__ = (CheckConstraint("purpose IN ('reset', 'verify')", name="ck_account_token_purpose"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(16), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    used_at = db.Column(db.DateTime(timezone=True))


class AuthRateLimit(db.Model):
    __tablename__ = "auth_rate_limits"

    key = db.Column(db.String(64), primary_key=True)
    attempts = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
