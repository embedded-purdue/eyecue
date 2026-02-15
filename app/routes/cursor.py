from flask import Blueprint, request, jsonify
import sys
import os

# Add parent directory to path to import CursorController
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from CursorController import CursorController

cursor_bp = Blueprint('cursor', __name__, url_prefix='/cursor')


def _cursor_enabled() -> bool:
    return os.getenv("EYE_ENABLE_CURSOR", "").lower() in {"1", "true", "yes", "on"}


@cursor_bp.route('/update', methods=["POST"])
def update():
    payload = request.get_json(silent=True) or {}
    x = payload.get("x")
    y = payload.get("y")
    mode = payload.get("mode", "abs")

    if x is None or y is None:
        return jsonify({"ok": False, "error": "x and y are required"}), 400

    try:
        x_val = float(x)
        y_val = float(y)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "x and y must be numbers"}), 400

    if _cursor_enabled():
        if mode == "rel":
            pyautogui.moveRel(x_val, y_val)
        else:
            pyautogui.moveTo(x_val, y_val)

    return jsonify({"ok": True}), 200
