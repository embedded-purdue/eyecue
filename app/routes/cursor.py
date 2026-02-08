from flask import Blueprint
import pyautogui
from flask import request, jsonify

cursor_bp = Blueprint('cursor', __name__, url_prefix='/cursor')

@cursor_bp.route('/update', methods=["POST"])
def update():
    if request.method == 'POST':
        x_pos = request.form.get('xPos')
        y_pos = request.form.get('yPos')

    return jsonify({"message": "ok"}), 200

if __name__ == "__main__":
    pyautogui.moveTo(100, 100)