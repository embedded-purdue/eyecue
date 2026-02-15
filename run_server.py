#!/usr/bin/env python3
"""
Run Flask development server for EyeCue app
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_cors import CORS
from app.routes.serial import serial_bp
from app.routes.cursor import cursor_bp
from app.routes.prefs import prefs_bp

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Register blueprints
app.register_blueprint(serial_bp)
app.register_blueprint(cursor_bp)
app.register_blueprint(prefs_bp)

@app.route("/")
def index():
    return {"status": "EyeCue API running", "version": "1.0.0"}

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    print("Starting EyeCue Flask server...")
    print("Server will be available at http://127.0.0.1:5001")
    app.run(debug=True, host='127.0.0.1', port=5001, use_reloader=False, threaded=True)
