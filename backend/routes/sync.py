from flask import Blueprint, jsonify
from sync import sync_user, sync_all

sync_bp = Blueprint("sync", __name__)


@sync_bp.route("/api/users/<user_id>/sync", methods=["POST"])
def trigger_sync(user_id):
    """Trigger a Nessie sync for a specific user."""
    try:
        result = sync_user(user_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sync_bp.route("/api/sync", methods=["POST"])
def trigger_sync_all():
    """Trigger a Nessie sync for all users."""
    try:
        results = sync_all()
        return jsonify({"users_synced": len(results), "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
