"""Additive, opt-in premium API. No guards are attached to existing public routes."""
import csv
from io import StringIO

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from grid_monitor.extensions import db
from grid_monitor.services.entitlements import premium_error, require_pro
from grid_monitor.services.geographic_hierarchy import HierarchyNotFound, hierarchy_detail
from grid_monitor.services.premium_analytics import (
    CSV_FIELDS, PremiumQueryError, generation_analysis, parse_window, validate_query,
)
from grid_monitor.subscription_models import utc_now

premium_bp = Blueprint("premium", __name__, url_prefix="/api/pro")


@premium_bp.before_request
def bound_request():
    if len(request.query_string) > 1024 or request.content_length:
        return premium_error("invalid_request", 400)


@premium_bp.errorhandler(PremiumQueryError)
def invalid_query(error):
    return jsonify(ok=False, code="invalid_query", message=str(error),
                   response_timestamp=utc_now().isoformat()), 400


@premium_bp.errorhandler(SQLAlchemyError)
def data_unavailable(error):
    db.session.rollback()
    current_app.logger.warning("premium_data_unavailable error_type=%s", type(error).__name__)
    return premium_error("data_unavailable", 503)


@premium_bp.get("/generation-analysis")
@require_pro("extended_history")
def generation_report():
    start, end = parse_window(request.args)
    return jsonify(ok=True, response_timestamp=utc_now().isoformat(),
                   data=generation_analysis(start, end))


@premium_bp.get("/exports/generation.csv")
@require_pro("advanced_exports")
def generation_export():
    start, end = parse_window(request.args)
    report = generation_analysis(start, end)
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    # Fixed numeric/date columns only: no user/source text can become spreadsheet formulas.
    writer.writerows(report["daily"])
    response = Response(output.getvalue(), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="npd-generation-daily-{start}-{end}.csv"'
    response.headers["X-Data-Grade"] = "stored-source-observations"
    response.headers["X-Window-End-Exclusive"] = end.isoformat()
    response.headers["X-Data-Calculated-At"] = report["calculated_at"]
    response.headers["Link"] = '</methodology>; rel="describedby", </data-sources>; rel="describedby"'
    return response


@premium_bp.get("/towns/<slug>")
@require_pro("town_intelligence")
def town_preview(slug):
    validate_query(request.args, set())
    try:
        data = hierarchy_detail("town", slug)
    except HierarchyNotFound:
        return premium_error("town_not_found", 404)
    # The existing public hierarchy remains unchanged, including the original metrics.
    data["data_lineage"] = {key: value for key, value in data["data_lineage"].items() if key != "dataset_path"}
    return jsonify(ok=True, response_timestamp=utc_now().isoformat(),
                   access="pro_preview" if current_app.config.get("PRO_PREVIEW_ENABLED", True) else "pro",
                   data_grade="planning_estimate", data=data)
