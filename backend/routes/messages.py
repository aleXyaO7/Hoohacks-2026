from flask import Blueprint, request, jsonify
from db import get_supabase
from agents.conversation_agent import handle_message

messages_bp = Blueprint("messages", __name__)


@messages_bp.route("/api/users/<user_id>/chat", methods=["POST"])
def chat(user_id):
    """Send a message and get a contextual AI response.

    Body: { "message": "Can I afford dinner tonight?", "channel": "web" }
    Returns: { "response": "...", "context_used": {...} }
    """
    data = request.get_json()
    if "message" not in data:
        return jsonify({"error": "message is required"}), 400

    channel = data.get("channel", "web")

    try:
        result = handle_message(user_id, data["message"], channel=channel)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@messages_bp.route("/api/users/<user_id>/messages", methods=["POST"])
def send_message(user_id):
    """Store a raw message (no AI response). Used for logging or manual inserts."""
    data = request.get_json()
    if "content" not in data:
        return jsonify({"error": "content is required"}), 400

    row = {
        "user_id": user_id,
        "role": data.get("role", "user"),
        "channel": data.get("channel", "web"),
        "content": data["content"],
    }

    try:
        result = get_supabase().table("messages").insert(row).execute()
        return jsonify(result.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@messages_bp.route("/api/users/<user_id>/messages", methods=["GET"])
def list_messages(user_id):
    limit = request.args.get("limit", 100, type=int)
    channel = request.args.get("channel")

    try:
        query = (
            get_supabase()
            .table("messages")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .limit(limit)
        )
        if channel:
            query = query.eq("channel", channel)

        result = query.execute()
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
