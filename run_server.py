#!/usr/bin/env python3
"""Run Flask development server for EyeCue app."""

from __future__ import annotations

from app.app import create_app
from app.config import FLASK_HOST, FLASK_PORT


if __name__ == "__main__":
    print("Starting EyeCue Flask server...")
    print(f"Server will be available at http://{FLASK_HOST}:{FLASK_PORT}")
    create_app().run(debug=True, host=FLASK_HOST, port=FLASK_PORT, use_reloader=False, threaded=True)
