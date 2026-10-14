"""CSRF-protected account forms. Accounts are opt-in and never enable billing."""
from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash

from grid_monitor.extensions import db
from grid_monitor.services.accounts import (
    consume_token, csrf, normalize_email, queue_account_email, throttle, validate_password,
)
from grid_monitor.services.entitlements import entitlement_snapshot
from grid_monitor.services.subscriptions import normalize_currency
from grid_monitor.subscription_models import User, UserSubscription, session_identifier, utc_now

accounts_bp = Blueprint("accounts", __name__)


def _form(kind, title, *, error=None, notice=None, status=200):
    return render_template("accounts/form.html", kind=kind, title=title, error=error, notice=notice), status


@accounts_bp.before_request
def protect_account_request():
    if not current_app.config.get("ACCOUNTS_ENABLED"):
        abort(404)
    if request.method == "POST":
        if request.content_length is not None and request.content_length > 16384:
            abort(413)
        csrf.protect()


@accounts_bp.after_request
def secure_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
    )
    response.vary.add("Cookie")
    return response


@accounts_bp.errorhandler(CSRFError)
def csrf_error(error):
    return _form("message", "Request expired", error="Refresh the page and try again.", status=400)


@accounts_bp.errorhandler(SQLAlchemyError)
def database_error(error):
    db.session.rollback()
    current_app.logger.warning("account_database_unavailable error_type=%s", type(error).__name__)
    return _form("message", "Account service unavailable", error="Please try again later.", status=503)


def _limited(action, email=""):
    if not throttle(action, email):
        response, status = _form("message", "Please try again later", error="Too many attempts. Try again in 15 minutes.", status=429)
        return response, status, {"Retry-After": "900"}
    return None


@accounts_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return _form("register", "Create your account")
    limited = _limited("register")
    if limited:
        return limited
    try:
        email = normalize_email(request.form.get("email", ""))
        password = validate_password(request.form.get("password", ""))
        currency = normalize_currency(request.form.get("currency"))
    except ValueError as exc:
        return _form("register", "Create your account", error=str(exc), status=400)
    if request.form.get("accept_terms") != "yes":
        return _form("register", "Create your account", error="Please accept the Terms of Use and Privacy Policy.", status=400)
    # Hash in both the duplicate and new-account paths; never accept plan/role fields.
    user = User(email=email)
    user.set_password(password)
    try:
        db.session.add(user)
        db.session.flush()
        db.session.add(UserSubscription(user_id=user.id, plan_code="community", currency=currency,
                                       billing_amount_minor=0, status="free"))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    queue_account_email(email, "verify")
    return _form("message", "Check your account", notice=(
        "If this address is eligible, your account is ready. Check your email when verification is enabled, then sign in."
    ))


@accounts_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return _form("login", "Sign in")
    limited = _limited("login")
    if limited:
        return limited
    try:
        email = normalize_email(request.form.get("email", ""))
    except ValueError:
        email = ""
    if email:
        # The IP budget was counted above; this adds a shared per-address budget.
        limited = _limited("login-address", email)
        if limited:
            return limited
    password = request.form.get("password", "")
    if len(password) > 128 or len(password.encode("utf-8")) > 512:
        password = ""
    user = User.query.filter_by(email=email).first() if email else None
    hashed = user.password_hash if user else current_app.extensions["account_dummy_hash"]
    valid = check_password_hash(hashed, password)
    if not user or not valid or not user.is_active or (
            current_app.config.get("AUTH_EMAIL_VERIFICATION_REQUIRED") and not user.email_verified_at):
        return _form("login", "Sign in", error="Unable to sign in. Check your credentials and email verification.", status=401)
    user.last_login_at = utc_now()
    db.session.commit()
    session.clear()
    session.permanent = True
    session["account_issued_at"] = utc_now().timestamp()
    login_user(user, remember=False, fresh=True)
    # No user-supplied next/callback URL is accepted.
    return redirect(url_for("accounts.account"), code=303)


@accounts_bp.post("/logout")
@login_required
def logout():
    current_user.session_token = session_identifier()
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for("accounts.login"), code=303)


@accounts_bp.get("/account")
@login_required
def account():
    return render_template("accounts/dashboard.html", title="Your account",
                           entitlements=entitlement_snapshot(current_user))


def _email_request(purpose):
    kind = "forgot" if purpose == "reset" else "resend"
    title = "Reset your password" if purpose == "reset" else "Verify your email"
    if not current_app.config.get("AUTH_EMAIL_ENABLED"):
        return _form("message", title, error="Email recovery is unavailable. Please contact support.", status=503)
    if request.method == "GET":
        return _form(kind, title)
    limited = _limited("email")
    if limited:
        return limited
    try:
        email = normalize_email(request.form.get("email", ""))
    except ValueError:
        email = ""
    if email:
        limited = _limited("email-address", email)
        if limited:
            return limited
        queue_account_email(email, purpose)
    # Unknown/known addresses, mail outages and queue saturation get the same response.
    return _form("message", "Check your email", notice="If the address is eligible, an email will arrive shortly. You can request another link later.")


@accounts_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    return _email_request("reset")


@accounts_bp.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    return _email_request("verify")


@accounts_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        return _form("reset", "Choose a new password")
    limited = _limited("token")
    if limited:
        return limited
    try:
        password = validate_password(request.form.get("password", ""))
    except ValueError as exc:
        return _form("reset", "Choose a new password", error=str(exc), status=400)
    if not consume_token(request.form.get("token") or request.form.get("manual_token", ""), "reset", password):
        return _form("reset", "Choose a new password", error="This link is invalid or expired. Request another email.", status=400)
    logout_user()
    session.clear()
    return _form("message", "Password updated", notice="Your sessions have been signed out. Sign in with your new password.")


@accounts_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if request.method == "GET":
        return _form("verify", "Confirm your email")
    limited = _limited("token")
    if limited:
        return limited
    if not consume_token(request.form.get("token") or request.form.get("manual_token", ""), "verify"):
        return _form("verify", "Confirm your email", error="This link is invalid or expired. Request another email.", status=400)
    return _form("message", "Email verified", notice="Your email is verified. You can now sign in.")
