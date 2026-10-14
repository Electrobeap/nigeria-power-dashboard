"""Private sandbox billing pages. The sole CSRF exemption uses raw-body HMAC."""
from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError

from grid_monitor.billing_models import BillingAccount, BillingPayment
from grid_monitor.extensions import db
from grid_monitor.routes.accounts import secure_response
from grid_monitor.services.accounts import csrf, throttle
from grid_monitor.services.billing import aware, enqueue_internal, initialize_checkout, receive_webhook
from grid_monitor.services.entitlements import entitlement_snapshot
from grid_monitor.services.paystack import BillingError, provider, sandbox_enabled
from grid_monitor.subscription_models import UserSubscription, utc_now

billing_bp = Blueprint("billing", __name__)


@billing_bp.before_request
def protect():
    if not current_app.config.get("ACCOUNTS_ENABLED") or not current_app.config.get("SUBSCRIPTIONS_ENABLED"):
        abort(404)
    if request.endpoint != "billing.dashboard" and not sandbox_enabled():
        abort(404)
    if request.endpoint == "billing.webhook":
        return
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.is_active or not current_user.email_verified_at:
        abort(403)
    if request.method == "POST":
        if request.content_length is not None and request.content_length > 16384:
            abort(413)
        csrf.protect()
        if request.args or set(request.form) - {"csrf_token"} or (
                request.is_json and request.get_json(silent=True) not in (None, {})):
            abort(400)
        if not throttle("billing", current_user.email):
            abort(429)


@billing_bp.after_request
def headers(response):
    response = secure_response(response)
    if sandbox_enabled():
        # Browsers can enforce form-action on the POST's final redirect target.
        response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace(
            "form-action 'self';", "form-action 'self' https://checkout.paystack.com https://paystack.com;")
    return response


@billing_bp.errorhandler(BillingError)
def billing_error(error):
    db.session.rollback()
    current_app.logger.warning("sandbox_billing_request_failed code=%s", error.code)
    return render_template("accounts/form.html", kind="message", title="Billing unavailable",
        error="Billing could not be completed. No access was granted from this request.",
        notice="Your existing public access is unchanged."), 503 if error.retryable else 409


@billing_bp.errorhandler(SQLAlchemyError)
def database_error(error):
    db.session.rollback()
    current_app.logger.warning("sandbox_billing_database_unavailable error_type=%s", type(error).__name__)
    return {"ok": False, "code": "billing_unavailable"}, 503


@billing_bp.errorhandler(CSRFError)
def csrf_error(error):
    return {"ok": False, "code": "csrf_failed"}, 400


def owned_account():
    account = db.session.get(BillingAccount, current_user.id)
    if not account:
        abort(404)
    return account


@billing_bp.get("/account/billing")
def dashboard():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        abort(400)
    if not 1 <= page <= 10000:
        abort(400)
    account = db.session.get(BillingAccount, current_user.id)
    contract = db.session.get(UserSubscription, account.subscription_id) if account else None
    rows = (BillingPayment.query.filter_by(subscription_id=contract.id).order_by(BillingPayment.id.desc())
            .offset((page - 1) * 20).limit(21).all() if contract else [])
    return render_template("accounts/billing.html", title="Subscription and billing", account=account,
        contract=contract, payments=rows[:20], page=page, has_next=len(rows) > 20,
        entitlements=entitlement_snapshot(current_user), sandbox=sandbox_enabled(),
        utc=aware)


@billing_bp.post("/billing/paystack/checkout")
@billing_bp.post("/api/billing/paystack/initialize")
def checkout():
    return redirect(initialize_checkout(current_user), code=303)


@billing_bp.get("/billing/paystack/callback")
def callback():
    if set(request.args) - {"reference", "trxref"} or any(len(request.args.getlist(k)) != 1 for k in request.args):
        abort(400)
    reference = request.args.get("reference")
    if not reference or (request.args.get("trxref") and request.args["trxref"] != reference):
        abort(400)
    account = owned_account()
    if reference != account.checkout_reference:
        abort(404)
    enqueue_internal("verify", {"reference": reference}, "callback:" + reference)
    return redirect(url_for("billing.dashboard"), code=303)


@billing_bp.post("/billing/paystack/refresh")
def refresh():
    account = owned_account()
    bucket = int(utc_now().timestamp()) // 60
    enqueue_internal("reconcile", {"user_id": account.user_id}, f"manual-reconcile:{account.user_id}:{bucket}")
    return redirect(url_for("billing.dashboard"), code=303)


@billing_bp.post("/billing/paystack/cancel")
def cancel():
    account = owned_account()
    bucket = int(utc_now().timestamp()) // 60
    enqueue_internal("command.cancel", {"user_id": account.user_id}, f"cancel:{account.user_id}:{bucket}")
    return redirect(url_for("billing.dashboard"), code=303)


@billing_bp.post("/billing/paystack/manage")
def manage():
    account = owned_account()
    contract = db.session.get(UserSubscription, account.subscription_id)
    if not contract.provider_subscription_reference:
        abort(409)
    return redirect(provider().manage(contract.provider_subscription_reference), code=303)


@billing_bp.post("/api/billing/paystack/webhook")
def webhook():
    if request.content_length is not None and request.content_length > 65536:
        abort(413)
    raw = request.stream.read(65537)
    if len(raw) > 65536:
        abort(413)
    try:
        inserted = receive_webhook(raw, request.headers.get("x-paystack-signature", ""))
    except BillingError as error:
        return {"ok": False, "code": error.code}, 401 if error.code == "invalid_webhook_signature" else 400
    return {"ok": True, "queued": inserted}, 200
