"""Read-only AI investigation endpoint; premium + CSRF + shared rate limits."""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError

from grid_monitor.services.accounts import csrf, throttle
from grid_monitor.services.agentic_intelligence import AgentUnavailable, investigate
from grid_monitor.services.entitlements import premium_error, require_pro
from grid_monitor.extensions import db

agent_bp = Blueprint("agent", __name__, url_prefix="/api/pro/agent")


@agent_bp.before_request
def agent_request_policy():
    if not current_app.config.get("AGENTIC_ENABLED", False):
        return premium_error("feature_unavailable", 404)
    if request.content_length is None or request.content_length > 2048:
        return premium_error("request_too_large", 413)
    if request.mimetype != "application/json":
        return premium_error("json_required", 415)
    csrf.protect()


@agent_bp.errorhandler(CSRFError)
def invalid_csrf(error):
    return premium_error("invalid_csrf", 400)


@agent_bp.post("/query")
@require_pro("agentic_insights")
def query():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"question"}:
        return premium_error("invalid_request", 400)
    question = payload.get("question")
    if not isinstance(question, str) or not 8 <= len(question.strip()) <= 600:
        return premium_error("invalid_question", 400)
    try:
        if not throttle("agentic-investigation", str(current_user.id)):
            response, status = premium_error("rate_limited", 429)
            response.headers["Retry-After"] = "900"
            return response, status
        result = investigate(question)
        response = jsonify(ok=True, **result)
        response.headers["X-Data-Grade"] = "mixed-observational-evidence"
        return response
    except (SQLAlchemyError, AgentUnavailable) as exc:
        db.session.rollback()
        current_app.logger.warning("agent_unavailable error_type=%s", type(exc).__name__)
        return premium_error("agent_unavailable", 503)
    except Exception as exc:
        current_app.logger.exception("agent_error error_type=%s", type(exc).__name__)
        return premium_error("agent_unavailable", 503)
