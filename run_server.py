#!/usr/bin/env python3
"""
Run Flask development server for EyeCue app
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from app.routes.serial import serial_bp
from app.routes.cursor import cursor_bp

app = Flask(__name__)

# Register blueprints
app.register_blueprint(serial_bp)
app.register_blueprint(cursor_bp)

@app.route("/")
def index():
    return {"status": "EyeCue API running", "version": "1.0.0"}

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    print("Starting EyeCue Flask server...")
    print("Server will be available at http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=True)
