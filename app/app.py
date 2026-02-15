"""
Flask core routes for the EyeCue app.
"""

from flask import Flask, jsonify

from routes.cursor import cursor_bp
from routes.serial import serial_bp
from routes.prefs import prefs_bp


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return ""

    @app.route("/health")
    def health():
        return jsonify({"ok": True}), 200

    app.register_blueprint(serial_bp)
    app.register_blueprint(cursor_bp)
    app.register_blueprint(prefs_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
