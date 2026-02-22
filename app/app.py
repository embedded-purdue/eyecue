"""Flask application factory for EyeCue desktop runtime."""

from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS

from app.config import FLASK_HOST, FLASK_PORT
from app.routes.app_state import app_state_bp
from app.routes.calibration import calibration_bp
from app.routes.cursor import cursor_bp
from app.routes.ingest import ingest_bp
from app.routes.internal import internal_bp
from app.routes.prefs import prefs_bp
from app.routes.runtime import runtime_bp
from app.routes.serial import serial_bp


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    @app.route("/")
    def index():
        return jsonify({"status": "EyeCue API running", "version": "2.0.0"}), 200

    @app.route("/health")
    def health():
        return jsonify({"ok": True}), 200

    app.register_blueprint(app_state_bp)
    app.register_blueprint(runtime_bp)
    app.register_blueprint(serial_bp)
    app.register_blueprint(cursor_bp)
    app.register_blueprint(prefs_bp)
    app.register_blueprint(calibration_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(internal_bp)

    return app


if __name__ == "__main__":
    create_app().run(
        debug=True,
        host=FLASK_HOST,
        port=FLASK_PORT,
        use_reloader=False,
        threaded=True,
    )
