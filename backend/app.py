import sys
import os

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
from routes.agents import agents_bp


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
    app.register_blueprint(agents_bp)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001, use_reloader=False)
