from flask import Blueprint, request, jsonify
from db import get_supabase

snapshots_bp = Blueprint("snapshots", __name__)


@snapshots_bp.route("/api/users/<user_id>/snapshots", methods=["POST"])
def create_snapshot(user_id):
    """Store a financial snapshot (called by the risk agent after evaluation)."""
    data = request.get_json()
    row = {
        "user_id": user_id,
        "balance": data.get("balance"),
        "risk_level": data.get("risk_level"),
        "data": data.get("data", {}),
    }

    try:
        result = get_supabase().table("snapshots").insert(row).execute()
        return jsonify(result.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@snapshots_bp.route("/api/users/<user_id>/snapshots/latest", methods=["GET"])
def get_latest_snapshot(user_id):
    try:
        result = (
            get_supabase()
            .table("snapshots")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "No snapshots found"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@snapshots_bp.route("/api/users/<user_id>/snapshots", methods=["GET"])
def list_snapshots(user_id):
    limit = request.args.get("limit", 20, type=int)
    try:
        result = (
            get_supabase()
            .table("snapshots")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
