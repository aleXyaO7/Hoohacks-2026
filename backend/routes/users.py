from flask import Blueprint, request, jsonify
from db import get_supabase
from nessie import query

NESSIE_BASE = "http://api.nessieisreal.com"

users_bp = Blueprint("users", __name__)


@users_bp.route("/api/users", methods=["POST"])
def create_user():
    """Create a new user: provisions a Nessie customer + Checking account,
    then stores everything in Supabase."""
    data = request.get_json()
    required = ["first_name", "last_name"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    first, last = data["first_name"], data["last_name"]

    try:
        # 1) Create customer in Nessie (use query directly to get the ID back)
        nessie_resp = query(f"{NESSIE_BASE}/customers", {
            "first_name": first,
            "last_name": last,
            "address": {
                "street_number": "1",
                "street_name": "Main St",
                "city": "Charlottesville",
                "state": "VA",
                "zip": "22903",
            },
        })
        if nessie_resp.status_code != 201:
            return jsonify({"error": "Failed to create Nessie customer",
                            "details": nessie_resp.text}), 502

        nessie_customer_id = nessie_resp.json()["objectCreated"]["_id"]

        # 2) Create a default Checking account in Nessie
        acct_resp = query(
            f"{NESSIE_BASE}/customers/{nessie_customer_id}/accounts",
            {
                "type": "Checking",
                "nickname": f"{first}'s Checking",
                "rewards": 0,
                "balance": data.get("initial_balance", 0),
            },
        )
        nessie_account = None
        if acct_resp.status_code == 201:
            nessie_account = acct_resp.json()["objectCreated"]

        # 3) Store user in Supabase
        user_row = {
            "first_name": first,
            "last_name": last,
            "nessie_customer_id": nessie_customer_id,
            "phone": data.get("phone"),
        }
        result = get_supabase().table("users").insert(user_row).execute()
        user = result.data[0]

        # 4) Store the default account in Supabase (if created)
        if nessie_account:
            get_supabase().table("accounts").insert({
                "user_id": user["id"],
                "nessie_account_id": nessie_account["_id"],
                "type": nessie_account.get("type", "Checking"),
                "balance": nessie_account.get("balance", 0),
            }).execute()

        return jsonify(user), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/api/users/login", methods=["POST"])
def login():
    """Look up an existing user by first + last name."""
    data = request.get_json()
    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()

    if not first or not last:
        return jsonify({"error": "first_name and last_name are required"}), 400

    try:
        result = (
            get_supabase()
            .table("users")
            .select("*")
            .ilike("first_name", first)
            .ilike("last_name", last)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "No account found with that name"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/api/users/<user_id>", methods=["GET"])
def get_user(user_id):
    try:
        result = get_supabase().table("users").select("*").eq("id", user_id).execute()
        if not result.data:
            return jsonify({"error": "User not found"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/api/users/by-nessie/<nessie_id>", methods=["GET"])
def get_user_by_nessie(nessie_id):
    try:
        result = (
            get_supabase()
            .table("users")
            .select("*")
            .eq("nessie_customer_id", nessie_id)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "User not found"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/api/users/<user_id>/goals", methods=["PUT"])
def update_goals(user_id):
    data = request.get_json()
    allowed = ["monthly_income", "monthly_expenses", "savings_goal", "debt", "current_savings"]
    updates = {k: data[k] for k in allowed if k in data}

    if not updates:
        return jsonify({"error": "No valid fields provided"}), 400

    try:
        result = (
            get_supabase()
            .table("users")
            .update(updates)
            .eq("id", user_id)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "User not found"}), 404
        return jsonify(result.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
