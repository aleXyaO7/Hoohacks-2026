from flask import Blueprint, request, jsonify
from db import get_supabase

transactions_bp = Blueprint("transactions", __name__)

# Max rows returned for list endpoints (most recent first).
MAX_TRANSACTIONS_LIMIT = 200


@transactions_bp.route("/api/accounts/<account_id>/transactions", methods=["GET"])
def list_transactions(account_id):
    limit = request.args.get("limit", MAX_TRANSACTIONS_LIMIT, type=int)
    limit = max(1, min(limit or MAX_TRANSACTIONS_LIMIT, MAX_TRANSACTIONS_LIMIT))
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
    """Get recent transactions across all accounts for a user (newest first, capped)."""
    limit = request.args.get("limit", MAX_TRANSACTIONS_LIMIT, type=int)
    limit = max(1, min(limit or MAX_TRANSACTIONS_LIMIT, MAX_TRANSACTIONS_LIMIT))

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
