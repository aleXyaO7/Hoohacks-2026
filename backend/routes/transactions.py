from flask import Blueprint, request, jsonify
from db import get_supabase

transactions_bp = Blueprint("transactions", __name__)


@transactions_bp.route("/api/accounts/<account_id>/transactions", methods=["GET"])
def list_transactions(account_id):
    limit = request.args.get("limit", 50, type=int)
    category = request.args.get("category")

    try:
        query = (
            get_supabase()
            .table("transactions")
            .select("*")
            .eq("account_id", account_id)
            .order("transaction_date", desc=True)
            .limit(limit)
        )
        if category:
            query = query.eq("category", category)

        result = query.execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@transactions_bp.route("/api/accounts/<account_id>/transactions", methods=["POST"])
def record_transactions(account_id):
    """Record one or more transactions (used by the sync service).

    Accepts either a single object or a list of objects.
    Duplicates are silently skipped via the nessie_transaction_id unique constraint.
    """
    data = request.get_json()
    rows = data if isinstance(data, list) else [data]

    for row in rows:
        row["account_id"] = account_id
        if "type" not in row:
            row["type"] = "purchase"

    try:
        result = (
            get_supabase()
            .table("transactions")
            .upsert(rows, on_conflict="nessie_transaction_id")
            .execute()
        )
        return jsonify(result.data), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@transactions_bp.route("/api/users/<user_id>/transactions", methods=["GET"])
def list_user_transactions(user_id):
    """Get all transactions across all accounts for a user."""
    limit = request.args.get("limit", 100, type=int)

    try:
        accounts = (
            get_supabase()
            .table("accounts")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )
        account_ids = [a["id"] for a in accounts.data]
        if not account_ids:
            return jsonify([])

        result = (
            get_supabase()
            .table("transactions")
            .select("*")
            .in_("account_id", account_ids)
            .order("transaction_date", desc=True)
            .limit(limit)
            .execute()
        )
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
