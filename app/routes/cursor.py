from flask import Blueprint, request, jsonify
import sys
import os

# Add parent directory to path to import CursorController
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from CursorController import CursorController

cursor_bp = Blueprint('cursor', __name__, url_prefix='/cursor')

@cursor_bp.route('/update', methods=["POST"])
def update():
    if request.method == 'POST':
        x_pos = request.form.get('xPos')
        y_pos = request.form.get('yPos')

    control = CursorController(0, 56.8, 16.3, -16.3, 0, 0, 60)
    control.update_target(0, -17.3, 0, 0)

    return jsonify({"message": "ok"}), 200

if __name__ == "__main__":
    control = CursorController(0, 56.8, 16.3, -16.3, 0, 0, 60)
    control.update_target(0, -17.3, 0, 0)