from flask import Blueprint, jsonify
from agents.risk_agent import assess_risk
from agents.notification_agent import should_alert
from agents.orchestrator import run_pipeline, run_pipeline_all, assess_only

agents_bp = Blueprint("agents", __name__)


@agents_bp.route("/api/users/<user_id>/pipeline", methods=["POST"])
def trigger_pipeline(user_id):
    """Run the full agent pipeline: sync → risk → notify → alert."""
    try:
        result = run_pipeline(user_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agents_bp.route("/api/pipeline", methods=["POST"])
def trigger_pipeline_all():
    """Run the full pipeline for all users."""
    try:
        results = run_pipeline_all()
        return jsonify({"users_processed": len(results), "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agents_bp.route("/api/users/<user_id>/risk", methods=["GET"])
def get_risk(user_id):
    """Run risk assessment only (no sync, no alerting)."""
    try:
        result = assess_only(user_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
