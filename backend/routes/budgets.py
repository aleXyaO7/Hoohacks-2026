from flask import Blueprint, request, jsonify
from db import get_supabase
from helpers import get_user_budgets, create_budget, get_active_budgets_usage

budgets_bp = Blueprint("budgets", __name__)


@budgets_bp.route("/api/users/<user_id>/budgets", methods=["POST"])
def upsert_budget(user_id):
    data = request.get_json()
    required = ["category", "amount", "start_date", "end_date"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        budget = create_budget(
            user_id,
            data["category"],
            data["amount"],
            data["start_date"],
            data["end_date"],
            account_id=data.get("account_id"),
        )
        if not budget:
            return jsonify({"error": "Failed to save budget"}), 500
        return jsonify(budget), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@budgets_bp.route("/api/users/<user_id>/budgets", methods=["GET"])
def list_budgets(user_id):
    try:
        return jsonify(get_user_budgets(user_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@budgets_bp.route("/api/users/<user_id>/budgets/active", methods=["GET"])
def active_budgets_usage(user_id):
    """Active budget periods (today in range) with spent vs limit."""
    try:
        return jsonify(get_active_budgets_usage(user_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@budgets_bp.route("/api/users/<user_id>/budgets/<category>", methods=["DELETE"])
def delete_budget(user_id, category):
    try:
        get_supabase().table("budgets").delete().eq("user_id", user_id).eq(
            "category", category
        ).execute()
        return "", 204
    except Exception as e:
        return jsonify({"error": str(e)}), 500
