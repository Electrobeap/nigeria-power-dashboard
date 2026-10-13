"""Policy foundation only. Route enforcement is a separately reviewed Stage 2."""
from flask import current_app

from grid_monitor.subscription_models import UserSubscription, utc_now

PREMIUM_FEATURES = {"extended_history", "advanced_exports", "town_intelligence"}
PUBLIC_FEATURES = {"national_dashboard", "regional_dashboard", "state_dashboard", "public_history",
                   "articles", "research"}


def active_subscription(user):
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    now = utc_now()
    return UserSubscription.query.filter(
        UserSubscription.user_id == user.id, UserSubscription.plan_code == "pro",
        UserSubscription.status.in_(("active", "cancelled")),
        UserSubscription.current_period_start <= now,
        UserSubscription.current_period_end > now,
    ).order_by(UserSubscription.current_period_end.desc()).first()


def entitlement_snapshot(user=None):
    subscription = active_subscription(user)
    return {
        "plan_code": "pro" if subscription else "community",
        "premium_access_active": subscription is not None,
        "active_until": subscription.current_period_end.isoformat() if subscription else None,
        "currency": subscription.currency if subscription else None,
        "pro_preview_enabled": bool(current_app.config.get("PRO_PREVIEW_ENABLED", True)),
        "enforcement_installed": False,
        "billing_enabled": False,
    }


def access_decision(feature, user=None):
    """Central decision contract for future guards, not an authorization decorator."""
    if feature in PUBLIC_FEATURES:
        return {"allowed": True, "reason": "public"}
    if feature not in PREMIUM_FEATURES:
        return {"allowed": False, "reason": "unknown_feature"}
    if feature == "town_intelligence" and current_app.config.get("PRO_PREVIEW_ENABLED", True):
        return {"allowed": True, "reason": "pro_preview", "data_grade": "planning_estimate"}
    if not (current_app.config.get("SUBSCRIPTIONS_ENABLED") and current_app.config.get("PREMIUM_GATING_ENABLED")):
        return {"allowed": True, "reason": "gating_disabled"}
    if (current_app.config.get("AUTH_EMAIL_VERIFICATION_REQUIRED")
            and (user is None or not getattr(user, "email_verified_at", None))):
        return {"allowed": False, "reason": "verification_required"}
    allowed = active_subscription(user) is not None
    return {"allowed": allowed, "reason": "active_pro" if allowed else "subscription_required"}
