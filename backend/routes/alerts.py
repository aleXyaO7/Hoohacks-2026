from flask import Blueprint, request, jsonify
from db import get_supabase

alerts_bp = Blueprint("alerts", __name__)


# ── Events ──────────────────────────────────────────────────────────

@alerts_bp.route("/api/users/<user_id>/events", methods=["POST"])
def create_event(user_id):
    """Record a detected event (called by the event detector)."""
    data = request.get_json()
    if "event_type" not in data:
        return jsonify({"error": "event_type is required"}), 400

    row = {
        "user_id": user_id,
        "event_type": data["event_type"],
        "payload": data.get("payload", {}),
    }

    try:
        result = get_supabase().table("events").insert(row).execute()
        return jsonify(result.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@alerts_bp.route("/api/users/<user_id>/events", methods=["GET"])
def list_events(user_id):
    limit = request.args.get("limit", 50, type=int)
    unprocessed_only = request.args.get("unprocessed", "false").lower() == "true"

    try:
        query = (
            get_supabase()
            .table("events")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if unprocessed_only:
            query = query.eq("processed", False)

        result = query.execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@alerts_bp.route("/api/events/<event_id>/processed", methods=["PATCH"])
def mark_event_processed(event_id):
    try:
        result = (
            get_supabase()
            .table("events")
            .update({"processed": True})
            .eq("id", event_id)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "Event not found"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Alerts ──────────────────────────────────────────────────────────

@alerts_bp.route("/api/users/<user_id>/alerts", methods=["POST"])
def create_alert(user_id):
    """Record a sent alert (called by the notification agent)."""
    data = request.get_json()
    row = {
        "user_id": user_id,
        "event_id": data.get("event_id"),
        "channel": data.get("channel", "dashboard"),
        "message": data["message"],
        "risk_level": data.get("risk_level"),
        "reasoning": data.get("reasoning", {}),
    }

    try:
        result = get_supabase().table("alerts").insert(row).execute()
        return jsonify(result.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@alerts_bp.route("/api/users/<user_id>/alerts", methods=["GET"])
def list_alerts(user_id):
    limit = request.args.get("limit", 50, type=int)
    try:
        result = (
            get_supabase()
            .table("alerts")
            .select("*")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .limit(limit)
            .execute()
        )
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
