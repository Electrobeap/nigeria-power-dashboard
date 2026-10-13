"""Public pricing only. No provider or checkout handlers are loaded in Stage 1."""
from flask import Blueprint, abort, jsonify, render_template, request
from grid_monitor.services.subscriptions import pricing_payload
from grid_monitor.services.social_meta import build_social_meta
from grid_monitor.services.structured_data import build_structured_data

subscription_bp = Blueprint("subscriptions", __name__)


def _pricing():
    try:
        return pricing_payload(request.args.get("currency"))
    except ValueError:
        abort(400, description="Choose NGN or USD.")


@subscription_bp.get("/pricing")
def pricing_page():
    pricing = _pricing()
    title = "Plans and Pricing"
    description = "Community access is free. Explore provisional NGN and USD Pro pricing. Checkout is not yet available."
    return render_template(
        "pricing.html", title=title, description=description, pricing=pricing,
        canonical_url=build_social_meta(title=title, description=description, path="/pricing")["url"],
        social_meta=build_social_meta(title=title, description=description, path="/pricing"),
        structured_data=build_structured_data(title=title, description=description, path="/pricing",
            breadcrumbs=[{"name": "Home", "path": "/"}, {"name": "Pricing", "path": "/pricing"}],
            page_type="WebPage", include_datasets=False),
    )


@subscription_bp.get("/api/subscriptions/pricing")
def pricing_api():
    return jsonify(_pricing())
