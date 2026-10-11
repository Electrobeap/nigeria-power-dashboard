from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

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


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(120))
    role = db.Column(db.String(32), nullable=False, default="user", index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    email_verified_at = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    subscriptions = db.relationship(
        "UserSubscription",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="desc(UserSubscription.created_at)",
    )
    payment_transactions = db.relationship("PaymentTransaction", back_populates="user", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def active_subscription(self):
        now = utc_now()
        for subscription in self.subscriptions:
            if subscription.status == "active" and (
                subscription.current_period_end is None or subscription.current_period_end >= now
            ):
                return subscription
        return None


class SubscriptionPlanPrice(db.Model):
    __tablename__ = "subscription_plan_prices"
    __table_args__ = (
        UniqueConstraint("plan_code", "currency", "version", name="uq_subscription_plan_price_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    plan_code = db.Column(db.String(50), nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    currency = db.Column(db.String(3), nullable=False, index=True)
    amount_minor = db.Column(db.Integer)
    interval = db.Column(db.String(16))
    version = db.Column(db.Integer, nullable=False, default=1, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    checkout_enabled = db.Column(db.Boolean, nullable=False, default=False)
    provider = db.Column(db.String(50))
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    effective_from = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    effective_until = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class PaymentProviderPlan(db.Model):
    __tablename__ = "payment_provider_plans"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "plan_code",
            "currency",
            "environment",
            name="uq_payment_provider_plan_currency_environment",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False, index=True)
    plan_code = db.Column(db.String(50), nullable=False, index=True)
    currency = db.Column(db.String(3), nullable=False, index=True)
    environment = db.Column(db.String(32), nullable=False, default="test", index=True)
    provider_plan_code = db.Column(db.String(255), nullable=False)
    amount_minor = db.Column(db.Integer)
    interval = db.Column(db.String(16))
    is_active = db.Column(db.Boolean, nullable=False, default=False, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class UserSubscription(db.Model):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_reference", name="uq_subscription_provider_reference"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_code = db.Column(db.String(50), nullable=False, default="community", index=True)
    currency = db.Column(db.String(3), nullable=False, default="NGN", index=True)
    billing_amount_minor = db.Column(db.Integer, nullable=False, default=0)
    price_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(32), nullable=False, default="free", index=True)
    provider = db.Column(db.String(50))
    provider_customer_reference = db.Column(db.String(255), index=True)
    provider_subscription_reference = db.Column(db.String(255), index=True)
    provider_plan_reference = db.Column(db.String(255))
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True), index=True)
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    cancelled_at = db.Column(db.DateTime(timezone=True))
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = db.relationship("User", back_populates="subscriptions")
    payment_transactions = db.relationship("PaymentTransaction", back_populates="subscription", lazy="dynamic")
    invoices = db.relationship("BillingInvoice", back_populates="subscription", lazy="dynamic")


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_reference", name="uq_payment_provider_reference"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("user_subscriptions.id", ondelete="SET NULL"), index=True)
    provider = db.Column(db.String(50), nullable=False, index=True)
    currency = db.Column(db.String(3), nullable=False, index=True)
    amount_minor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False, index=True)
    provider_reference = db.Column(db.String(255), nullable=False, index=True)
    provider_transaction_id = db.Column(db.String(255), index=True)
    provider_customer_reference = db.Column(db.String(255), index=True)
    provider_subscription_reference = db.Column(db.String(255), index=True)
    payment_channel = db.Column(db.String(64))
    paid_at = db.Column(db.DateTime(timezone=True), index=True)
    fees_minor = db.Column(db.Integer)
    settlement_amount_minor = db.Column(db.Integer)
    settlement_currency = db.Column(db.String(3))
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    raw_payload_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = db.relationship("User", back_populates="payment_transactions")
    subscription = db.relationship("UserSubscription", back_populates="payment_transactions")


class BillingInvoice(db.Model):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        UniqueConstraint("provider", "provider_invoice_reference", name="uq_invoice_provider_reference"),
    )

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("user_subscriptions.id", ondelete="SET NULL"), index=True)
    provider = db.Column(db.String(50), index=True)
    provider_invoice_reference = db.Column(db.String(255), index=True)
    currency = db.Column(db.String(3), nullable=False, index=True)
    amount_due_minor = db.Column(db.Integer, nullable=False)
    amount_paid_minor = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, index=True)
    period_start = db.Column(db.DateTime(timezone=True))
    period_end = db.Column(db.DateTime(timezone=True))
    due_at = db.Column(db.DateTime(timezone=True))
    paid_at = db.Column(db.DateTime(timezone=True))
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    subscription = db.relationship("UserSubscription", back_populates="invoices")


class PaymentWebhookEvent(db.Model):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_reference", name="uq_webhook_provider_event_reference"),
    )

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False, index=True)
    event_type = db.Column(db.String(120), nullable=False, index=True)
    event_reference = db.Column(db.String(255), nullable=False, index=True)
    processing_status = db.Column(db.String(32), nullable=False, default="received", index=True)
    raw_payload_json = db.Column(db.JSON, nullable=False, default=dict)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    processed_at = db.Column(db.DateTime(timezone=True))
    error_message = db.Column(db.Text)
