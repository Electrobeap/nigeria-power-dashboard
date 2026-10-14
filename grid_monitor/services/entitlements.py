"""Server-side policy for additive premium services; existing public routes stay free."""
from datetime import timezone
from functools import wraps

from flask import current_app, jsonify
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from grid_monitor.extensions import db
from grid_monitor.subscription_models import User, UserSubscription, utc_now

PREMIUM_FEATURES = {"extended_history", "advanced_exports", "town_intelligence"}
PUBLIC_FEATURES = {"national_dashboard", "regional_dashboard", "state_dashboard", "public_history",
                   "articles", "research"}


def premium_services_enabled():
    return all(current_app.config.get(name, False) for name in
               ("ACCOUNTS_ENABLED", "SUBSCRIPTIONS_ENABLED", "PREMIUM_GATING_ENABLED"))


def active_subscription(user):
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    now = utc_now()
    # Re-check identity and verification in the DB, never from request fields/cache.
    return UserSubscription.query.join(User, User.id == UserSubscription.user_id).filter(
        User.id == user.id, User.is_active.is_(True), User.email_verified_at.is_not(None),
        UserSubscription.plan_code == "pro",
        UserSubscription.status.in_(("active", "cancelled")),
        UserSubscription.current_period_start <= now,
        UserSubscription.current_period_end > now,
    ).order_by(UserSubscription.current_period_end.desc()).first()


def entitlement_snapshot(user=None):
    subscription = active_subscription(user)
    expires = subscription.current_period_end if subscription else None
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return {
        "plan_code": "pro" if subscription else "community",
        "premium_access_active": subscription is not None,
        "active_until": expires.isoformat() if expires else None,
        "currency": subscription.currency if subscription else None,
        "pro_preview_enabled": bool(current_app.config.get("PRO_PREVIEW_ENABLED", True)),
        "enforcement_installed": True,
        "enforcement_enabled": premium_services_enabled(),
        "billing_enabled": False,
    }


def access_decision(feature, user=None):
    if feature in PUBLIC_FEATURES:
        return {"allowed": True, "reason": "public"}
    if feature not in PREMIUM_FEATURES:
        return {"allowed": False, "reason": "unknown_feature", "status": 403}
    if feature == "town_intelligence" and current_app.config.get("PRO_PREVIEW_ENABLED", True):
        return {"allowed": True, "reason": "pro_preview", "data_grade": "planning_estimate"}
    if not premium_services_enabled():
        return {"allowed": False, "reason": "feature_unavailable", "status": 404}
    if user is None or not getattr(user, "is_authenticated", False):
        return {"allowed": False, "reason": "authentication_required", "status": 401}
    if not user.is_active:
        return {"allowed": False, "reason": "account_inactive", "status": 403}
    if not getattr(user, "email_verified_at", None):
        return {"allowed": False, "reason": "verification_required", "status": 403}
    allowed = active_subscription(user) is not None
    return {"allowed": allowed, "reason": "active_pro" if allowed else "subscription_required",
            "status": 200 if allowed else 403}


def premium_error(code, status):
    return jsonify(ok=False, code=code, response_timestamp=utc_now().isoformat(),
                   login_url="/login", pricing_url="/pricing"), status


def require_pro(feature):
    """Run on every request, including HEAD, before a loader or cache can execute."""
    if feature not in PREMIUM_FEATURES:
        raise ValueError("Unknown premium capability.")

    def decorate(view):
        @wraps(view)
        def guarded(*args, **kwargs):
            if not premium_services_enabled():
                return premium_error("feature_unavailable", 404)
            try:
                # Preview does not load a user or require account/subscription SQL.
                user = None if feature == "town_intelligence" and current_app.config.get("PRO_PREVIEW_ENABLED", True) else current_user
                decision = access_decision(feature, user)
            except SQLAlchemyError as exc:
                db.session.rollback()
                current_app.logger.warning("premium_authorization_unavailable error_type=%s", type(exc).__name__)
                return premium_error("authorization_unavailable", 503)
            if not decision["allowed"]:
                return premium_error(decision["reason"], decision["status"])
            return view(*args, **kwargs)
        return guarded
    return decorate
