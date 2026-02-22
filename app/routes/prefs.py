from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.prefs_utils import DEFAULT_PREFS, load_prefs, save_prefs
from app.services.runtime_context import calibration_service


prefs_bp = Blueprint("prefs", __name__, url_prefix="/prefs")


@prefs_bp.route("", methods=["GET"])
def get_prefs() -> tuple:
    return jsonify({"ok": True, "data": load_prefs()}), 200


@prefs_bp.route("", methods=["PUT"])
def update_prefs() -> tuple:
    payload = request.get_json(silent=True) or {}
    prefs = load_prefs()
    for key, value in payload.items():
        if key in DEFAULT_PREFS:
            prefs[key] = value
    for key, value in DEFAULT_PREFS.items():
        prefs.setdefault(key, value)
    save_prefs(prefs)
    return jsonify({"ok": True, "data": prefs}), 200


@prefs_bp.route("/calibration", methods=["POST"])
def save_calibration_compat() -> tuple:
    """Compatibility shim for the old calibration endpoint."""
    payload = request.get_json(silent=True) or {}
    try:
        session = calibration_service.complete_legacy_payload(payload)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    prefs = load_prefs()
    return jsonify({"ok": True, "data": {"prefs": prefs, "session": session}}), 200
