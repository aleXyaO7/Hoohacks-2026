from flask import Blueprint, request, jsonify
from db import get_supabase
from nessie import query

NESSIE_BASE = "http://api.nessieisreal.com"

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("/api/users/<user_id>/accounts", methods=["POST"])
def link_account(user_id):
    """Create a new account in Nessie and store it in Supabase."""
    data = request.get_json()
    account_type = data.get("type", "Checking")

    try:
        # Look up the user's nessie_customer_id
        user = (
            get_supabase()
            .table("users")
            .select("nessie_customer_id")
            .eq("id", user_id)
            .execute()
        )
        if not user.data:
            return jsonify({"error": "User not found"}), 404

        nessie_cid = user.data[0]["nessie_customer_id"]

        # Create account in Nessie
        resp = query(
            f"{NESSIE_BASE}/customers/{nessie_cid}/accounts",
            {
                "type": account_type,
                "nickname": data.get("nickname", f"{account_type} Account"),
                "rewards": data.get("rewards", 0),
                "balance": data.get("balance", 0),
            },
        )
        if resp.status_code != 201:
            return jsonify({"error": "Failed to create Nessie account",
                            "details": resp.text}), 502

        nessie_account = resp.json()["objectCreated"]

        # Store in Supabase
        row = {
            "user_id": user_id,
            "nessie_account_id": nessie_account["_id"],
            "type": nessie_account.get("type", account_type),
            "balance": nessie_account.get("balance", 0),
        }
        result = get_supabase().table("accounts").insert(row).execute()
        return jsonify(result.data[0]), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@accounts_bp.route("/api/users/<user_id>/accounts", methods=["GET"])
def list_accounts(user_id):
    try:
        result = (
            get_supabase()
            .table("accounts")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@accounts_bp.route("/api/accounts/<account_id>", methods=["GET"])
def get_account(account_id):
    try:
        result = (
            get_supabase()
            .table("accounts")
            .select("*")
            .eq("id", account_id)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "Account not found"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@accounts_bp.route("/api/accounts/<account_id>", methods=["PATCH"])
def update_account(account_id):
    data = request.get_json()
    allowed = ["balance", "last_synced_at"]
    updates = {k: data[k] for k in allowed if k in data}

    if not updates:
        return jsonify({"error": "No valid fields provided"}), 400

    try:
        result = (
            get_supabase()
            .table("accounts")
            .update(updates)
            .eq("id", account_id)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "Account not found"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
