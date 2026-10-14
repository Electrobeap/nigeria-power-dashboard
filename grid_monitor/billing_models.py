"""Sandbox-only audit tables. No foreign keys to electricity observations."""
from grid_monitor.extensions import db
from grid_monitor.subscription_models import utc_now


class BillingAccount(db.Model):
    __tablename__ = "billing_accounts"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("user_subscriptions.id"), nullable=False, unique=True)
    checkout_reference = db.Column(db.String(100), nullable=False, unique=True)
    plan_reference = db.Column(db.String(100), nullable=False)
    checkout_url = db.Column(db.String(512))
    checkout_status = db.Column(db.String(24), nullable=False, default="initializing")
    provider_status = db.Column(db.String(24), nullable=False, default="pending")
    provider_updated_at = db.Column(db.DateTime(timezone=True))
    next_payment_at = db.Column(db.DateTime(timezone=True))
    renewal_enabled = db.Column(db.Boolean, nullable=False, default=False)
    cancel_requested_at = db.Column(db.DateTime(timezone=True))
    last_reconciled_at = db.Column(db.DateTime(timezone=True))
    lease_token = db.Column(db.String(64))
    lease_until = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class BillingPayment(db.Model):
    __tablename__ = "billing_payments"
    __table_args__ = (
        db.CheckConstraint("currency = 'NGN'", name="ck_billing_payment_ngn"),
        db.CheckConstraint("amount_minor = 750000", name="ck_billing_payment_amount"),
        db.CheckConstraint("status IN ('success', 'failed', 'reversed')", name="ck_billing_payment_status"),
        db.CheckConstraint("period_end IS NULL OR period_end > period_start", name="ck_billing_payment_period"),
    )
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("user_subscriptions.id"), nullable=False, index=True)
    transaction_id = db.Column(db.String(32), nullable=False, unique=True)
    reference = db.Column(db.String(100), nullable=False, unique=True)
    currency = db.Column(db.String(3), nullable=False)
    amount_minor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False)
    paid_at = db.Column(db.DateTime(timezone=True))
    period_start = db.Column(db.DateTime(timezone=True))
    period_end = db.Column(db.DateTime(timezone=True))
    verified_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class BillingInvoice(db.Model):
    __tablename__ = "billing_invoices"
    invoice_code = db.Column(db.String(100), primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("user_subscriptions.id"), nullable=False, index=True)
    period_start = db.Column(db.DateTime(timezone=True), nullable=False)
    period_end = db.Column(db.DateTime(timezone=True), nullable=False)
    amount_minor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False)
    payment_reference = db.Column(db.String(100))
    observed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (
        db.CheckConstraint("period_end > period_start", name="ck_billing_invoice_period"),
        db.CheckConstraint("amount_minor = 750000", name="ck_billing_invoice_amount"),
    )


class BillingEvent(db.Model):
    __tablename__ = "billing_events"
    digest = db.Column(db.String(64), primary_key=True)
    event_type = db.Column(db.String(40), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending")
    attempts = db.Column(db.Integer, nullable=False, default=0)
    available_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    processed_at = db.Column(db.DateTime(timezone=True))
    lease_token = db.Column(db.String(64))
    last_error = db.Column(db.String(40))
