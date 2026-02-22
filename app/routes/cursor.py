from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.config import CURSOR_ENABLED
from app.services.runtime_context import runtime_store

try:
    import pyautogui
except Exception:  # pragma: no cover - optional runtime dependency
    pyautogui = None


cursor_bp = Blueprint("cursor", __name__, url_prefix="/cursor")


@cursor_bp.route("/update", methods=["POST"])
def update() -> tuple:
    body = request.get_json(silent=True) or {}
    if "x" not in body or "y" not in body:
        return jsonify({"ok": False, "error": "x and y are required"}), 400

    try:
        sample = runtime_store.ingest_cursor_sample(
            {
                "x": body.get("x"),
                "y": body.get("y"),
                "mode": body.get("mode", "abs"),
                "source": body.get("source", "api"),
                "ts_ms": body.get("ts_ms"),
                "confidence": body.get("confidence"),
                "raw": body,
            },
            default_source="api",
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    mode = body.get("mode", "abs")
    if CURSOR_ENABLED and pyautogui is not None:
        x = float(sample["x"])
        y = float(sample["y"])
        if mode == "rel":
            pyautogui.moveRel(x, y)
        else:
            pyautogui.moveTo(x, y)

    return jsonify({"ok": True, "data": sample}), 200
