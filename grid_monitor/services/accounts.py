"""Account security services. No billing, public-data queries, or scheduler hooks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import secrets
import smtplib
import ssl
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from flask import current_app, request, session
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import delete, inspect, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from grid_monitor.extensions import db
from grid_monitor.subscription_models import AccountToken, AuthRateLimit, SubscriptionPlanPrice, UserSubscription, User, session_identifier, utc_now

login_manager = LoginManager()
csrf = CSRFProtect()


def normalize_email(value):
    if not isinstance(value, str) or len(value) > 254:
        raise ValueError("Enter a valid email address.")
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError("Enter a valid email address.") from None


def validate_password(value):
    if not isinstance(value, str) or not 15 <= len(value) <= 128 or len(value.encode("utf-8")) > 512:
        raise ValueError("Use a password of 15 to 128 characters.")
    return value


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def init_accounts(app):
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "accounts.login"
    login_manager.session_protection = "strong"
    # Later stages must install and test every guard/payment handler before activation.
    if app.config.get("PREMIUM_GATING_ENABLED") or app.config.get("PAYSTACK_TEST_CHECKOUT_ENABLED") or app.config.get("LIVE_BILLING_ENABLED") or app.config.get("USD_CHECKOUT_ENABLED"):
        raise RuntimeError("Premium enforcement and checkout are not installed in Stage 1; keep activation flags disabled.")
    if not app.config.get("ACCOUNTS_ENABLED"):
        return
    if len(str(app.secret_key or "")) < 32 or app.secret_key == "dev-only-change-me":
        raise RuntimeError("Accounts require a strong SECRET_KEY of at least 32 characters.")
    base = urlsplit(app.config["APP_BASE_URL"])
    local = base.hostname in {"localhost", "127.0.0.1"}
    if (base.username or base.password or base.query or base.fragment or base.path not in {"", "/"}
            or not base.hostname or (base.scheme != "https" and not (local and app.testing))):
        raise RuntimeError("Account email links require a configured HTTPS APP_BASE_URL.")
    if not app.testing and not app.config["SESSION_COOKIE_SECURE"]:
        raise RuntimeError("Production account cookies require HTTPS and SESSION_COOKIE_SECURE=true.")
    if app.config.get("AUTH_EMAIL_VERIFICATION_REQUIRED") and not app.config.get("AUTH_EMAIL_ENABLED"):
        raise RuntimeError("Required email verification needs configured email delivery.")
    if app.config.get("AUTH_EMAIL_ENABLED") and not app.testing:
        if not app.config.get("AUTH_SMTP_HOST") or not app.config.get("AUTH_MAIL_FROM"):
            raise RuntimeError("Email delivery requires AUTH_SMTP_HOST and AUTH_MAIL_FROM.")
    app.extensions["account_dummy_hash"] = generate_password_hash(secrets.token_urlsafe(32), method="scrypt:32768:8:3")


@login_manager.user_loader
def load_user(identifier):
    if not current_app.config.get("ACCOUNTS_ENABLED") or not isinstance(identifier, str) or len(identifier) > 64:
        return None
    issued = session.get("account_issued_at")
    if not isinstance(issued, (int, float)) or utc_now().timestamp() - issued > 8 * 3600:
        session.clear()
        return None
    try:
        user = User.query.filter_by(session_token=identifier, is_active=True).first()
        if user and current_app.config.get("AUTH_EMAIL_VERIFICATION_REQUIRED") and not user.email_verified_at:
            return None
        return user
    except SQLAlchemyError:
        db.session.rollback()
        return None


def throttle(action, email=""):
    """Atomic, shared DB counters; IP/email are keyed hashes, never stored raw."""
    now = utc_now()
    window = 900
    bucket = int(now.timestamp()) // window
    ip = request.remote_addr or "unknown"
    hops = int(current_app.config.get("AUTH_TRUST_PROXY_HOPS", 0))
    if hops > 0 and len(request.access_route) >= hops:
        ip = request.access_route[-hops]
    dimensions = [("ip", ip, 30)]
    if email:
        dimensions.append(("account", email, 8))
    dialect = db.engine.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Account throttling supports PostgreSQL and SQLite.")
    for kind, value, limit in dimensions:
        key = hmac.new(str(current_app.secret_key).encode(),
                       f"{action}:{kind}:{value}:{bucket}".encode(), hashlib.sha256).hexdigest()
        stmt = insert(AuthRateLimit).values(key=key, attempts=1, expires_at=now + timedelta(seconds=window))
        stmt = stmt.on_conflict_do_update(index_elements=["key"],
                                          set_={"attempts": AuthRateLimit.attempts + 1}).returning(AuthRateLimit.attempts)
        attempts = db.session.execute(stmt).scalar_one()
        db.session.commit()
        if attempts > limit:
            return False
    # Bound cleanup work; it never touches user, contract, or energy records.
    old = select(AuthRateLimit.key).where(AuthRateLimit.expires_at < now).limit(100)
    db.session.execute(delete(AuthRateLimit).where(AuthRateLimit.key.in_(old)))
    db.session.commit()
    return True


def issue_token(user, purpose):
    token = secrets.token_urlsafe(32)
    # Serialize issuance with password changes and other delivery workers.
    user = db.session.execute(select(User).where(User.id == user.id).with_for_update()
                              .execution_options(populate_existing=True)).scalar_one()
    db.session.execute(delete(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == purpose))
    db.session.add(AccountToken(user_id=user.id, purpose=purpose, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                expires_at=utc_now() + timedelta(minutes=30 if purpose == "reset" else 1440)))
    db.session.commit()
    return token


def consume_token(token, purpose, password=None):
    if not isinstance(token, str) or len(token) != 43:
        return False
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = utc_now()
    record = AccountToken.query.filter_by(token_hash=token_hash, purpose=purpose, used_at=None).first()
    if not record or _aware(record.expires_at) <= now:
        return False
    user = db.session.execute(select(User).where(User.id == record.user_id).with_for_update()
                              .execution_options(populate_existing=True)).scalar_one_or_none()
    if not user or not user.is_active:
        return False
    used = db.session.execute(update(AccountToken).where(
        AccountToken.id == record.id, AccountToken.used_at.is_(None), AccountToken.expires_at > now,
    ).values(used_at=now)).rowcount
    if used != 1:
        db.session.rollback()
        return False
    if purpose == "reset":
        user.set_password(validate_password(password))
        user.session_token = session_identifier()
        # Every outstanding reset/verification token is invalid after a password change.
        db.session.execute(update(AccountToken).where(AccountToken.user_id == user.id).values(used_at=now))
    else:
        user.email_verified_at = now
    db.session.commit()
    return True


def _deliver_email(app, email, purpose):
    """Runs off-request; unknown and known addresses use the same queue path."""
    with app.app_context():
        try:
            user = User.query.filter_by(email=email, is_active=True).first()
            if not user or (purpose == "verify" and user.email_verified_at):
                return
            token = issue_token(user, purpose)
            path = "/reset-password" if purpose == "reset" else "/verify-email"
            link = app.config["APP_BASE_URL"].rstrip("/") + path + "#token=" + token
            message = EmailMessage()
            message["From"] = app.config["AUTH_MAIL_FROM"]
            message["To"] = user.email
            message["Subject"] = "Reset your Nigeria Power Data password" if purpose == "reset" else "Verify your Nigeria Power Data email"
            message.set_content(
                f"Open this one-time link to {'reset your password' if purpose == 'reset' else 'verify your email'}:\n\n"
                f"{link}\n\nThis link expires in {'30 minutes' if purpose == 'reset' else '24 hours'}."
                "\nIf you did not request this, ignore this message. Your account has not been changed."
            )
            if app.testing and app.config.get("AUTH_MAIL_SENDER"):
                app.config["AUTH_MAIL_SENDER"](message)
                return
            context = ssl.create_default_context()
            with smtplib.SMTP(app.config["AUTH_SMTP_HOST"], app.config["AUTH_SMTP_PORT"], timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                if app.config.get("AUTH_SMTP_USERNAME"):
                    smtp.login(app.config["AUTH_SMTP_USERNAME"], app.config["AUTH_SMTP_PASSWORD"])
                smtp.send_message(message)
        except Exception as exc:
            db.session.rollback()
            # Do not log SMTP errors, addresses, links, tokens or SQL parameter values.
            app.logger.warning("account_email_delivery_failed error_type=%s", type(exc).__name__)
        finally:
            db.session.remove()


def queue_account_email(email, purpose):
    if not current_app.config.get("AUTH_EMAIL_ENABLED"):
        return False
    app = current_app._get_current_object()
    if app.testing and app.config.get("AUTH_MAIL_SYNCHRONOUS"):
        _deliver_email(app, email, purpose)
        return True
    # Created only when explicitly enabled, bounded to avoid unbounded task/PII retention.
    executor, slots = app.extensions["account_mail_queue"]
    if not slots.acquire(blocking=False):
        return False
    try:
        future = executor.submit(_deliver_email, app, email, purpose)
        future.add_done_callback(lambda result: slots.release())
    except RuntimeError:
        slots.release()
        return False
    return True


def start_mail_queue(app):
    if app.config.get("ACCOUNTS_ENABLED") and app.config.get("AUTH_EMAIL_ENABLED"):
        app.extensions["account_mail_queue"] = (ThreadPoolExecutor(max_workers=1, thread_name_prefix="account-mail"),
                                                BoundedSemaphore(20))


def validate_account_schema(app):
    """Require a real, reviewed migration before production accounts can start."""
    if not app.config.get("ACCOUNTS_ENABLED") or app.testing:
        return
    try:
        inspector = inspect(db.engine)
        for model in (User, SubscriptionPlanPrice, UserSubscription, AccountToken, AuthRateLimit):
            columns = {item["name"] for item in inspector.get_columns(model.__tablename__)}
            if not set(model.__table__.columns.keys()).issubset(columns):
                raise RuntimeError("Account schema is incomplete; run reviewed migrations.")
        revision = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != "d13a20261013":
            raise RuntimeError("Account migration revision has not been verified.")
    except SQLAlchemyError:
        db.session.rollback()
        raise RuntimeError("Account schema verification failed; run reviewed migrations.") from None
    finally:
        db.session.remove()
