"""
Docstring for app.app

Flask core routes for the EyeCue app

Routes:
- 

"""

from flask import Flask
from .routes.serial import serial_bp

app = Flask(__name__)

@app.route("/")
def index():
    return ""

if __name__ == "__main__":
    app.register_blueprint(serial_bp)

    app.run(debug=True)