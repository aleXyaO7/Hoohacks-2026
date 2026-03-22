from flask import Blueprint, request, jsonify
from db import get_supabase

budgets_bp = Blueprint("budgets", __name__)


@budgets_bp.route("/api/users/<user_id>/budgets", methods=["POST"])
def upsert_budget(user_id):
    data = request.get_json()
    required = ["category", "amount", "start_date", "end_date"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    row = {
        "user_id": user_id,
        "category": data["category"],
        "amount": data["amount"],
        "start_date": data["start_date"],
        "end_date": data["end_date"],
        "account_id": data.get("account_id"),
    }

    try:
        result = (
            get_supabase()
            .table("budgets")
            .upsert(row, on_conflict="user_id,category")
            .execute()
        )
        return jsonify(result.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@budgets_bp.route("/api/users/<user_id>/budgets", methods=["GET"])
def list_budgets(user_id):
    try:
        result = (
            get_supabase()
            .table("budgets")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        return jsonify(result.data)
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
