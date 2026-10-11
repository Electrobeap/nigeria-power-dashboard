from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import current_app


PUBLIC_BASELINE_HOURS = 168
PREMIUM_HISTORY_HOURS = 8760


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def subscriptions_enabled() -> bool:
    return bool(current_app.config.get("SUBSCRIPTIONS_ENABLED"))


def entitlement_snapshot(user: Any | None = None) -> dict[str, Any]:
    """Returns a conservative entitlement view without activating gates.

    Access enforcement is intentionally deferred to the authorization PR. This
    function centralizes the shape so API/web code can later check one service
    instead of trusting JavaScript or displayed pricing labels.
    """
    plan_code = "community"
    status = "public"
    currency = None
    active_until = None
    if user is not None:
        subscription = getattr(user, "active_subscription", None)
        if subscription:
            plan_code = subscription.plan_code
            status = subscription.status
            currency = subscription.currency
            active_until = subscription.current_period_end or subscription.expires_at
    return {
        "subscriptions_enabled": subscriptions_enabled(),
        "plan_code": plan_code,
        "status": status,
        "currency": currency,
        "active_until": active_until.isoformat() if active_until else None,
        "public_baseline_hours": PUBLIC_BASELINE_HOURS,
        "premium_history_hours": PREMIUM_HISTORY_HOURS,
        "premium_access_active": bool(plan_code == "pro" and status == "active" and active_until and active_until > utc_now()),
    }


def requires_pro_for_hours(hours: float | int | None) -> bool:
    if not subscriptions_enabled():
        return False
    try:
        requested = float(hours or PUBLIC_BASELINE_HOURS)
    except (TypeError, ValueError):
        requested = PUBLIC_BASELINE_HOURS
    return requested > PUBLIC_BASELINE_HOURS
