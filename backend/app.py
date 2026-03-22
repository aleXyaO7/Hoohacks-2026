import sys
import os
import signal
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify
from flask_cors import CORS

from routes.users import users_bp
from routes.accounts import accounts_bp
from routes.transactions import transactions_bp
from routes.budgets import budgets_bp
from routes.snapshots import snapshots_bp
from routes.alerts import alerts_bp
from routes.messages import messages_bp
from routes.sync import sync_bp
from routes.dashboard import dashboard_bp

PORT = 5001


def free_port(port):
    """Kill any process currently listening on the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            if pid.isdigit() and int(pid) != os.getpid():
                os.kill(int(pid), signal.SIGKILL)
                print(f"Killed stale process {pid} on port {port}")
    except Exception:
        pass


def create_app():
    app = Flask(__name__)
    CORS(app)

    app.register_blueprint(users_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(snapshots_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(dashboard_bp)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    free_port(PORT)
    app = create_app()
    app.run(debug=True, port=PORT, use_reloader=False)
