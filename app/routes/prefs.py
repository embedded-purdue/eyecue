from flask import Blueprint, request, jsonify

from prefs_utils import load_prefs, save_prefs, DEFAULT_PREFS


prefs_bp = Blueprint("prefs", __name__, url_prefix="/prefs")


@prefs_bp.route("", methods=["GET"])
def get_prefs():
    return jsonify({"ok": True, "data": load_prefs()}), 200


@prefs_bp.route("", methods=["PUT"])
def update_prefs():
    payload = request.get_json(silent=True) or {}
    prefs = load_prefs()
    for key, value in payload.items():
        if key in DEFAULT_PREFS:
            prefs[key] = value
    for key in DEFAULT_PREFS.keys():
        prefs.setdefault(key, DEFAULT_PREFS[key])
    save_prefs(prefs)
    return jsonify({"ok": True, "data": prefs}), 200


@prefs_bp.route("/calibration", methods=["POST"])
def save_calibration():
    """Save calibration data"""
    payload = request.get_json(silent=True) or {}
    
    prefs = load_prefs()
    prefs['calibration_data'] = payload.get('calibration_data', [])
    prefs['calibration_timestamp'] = payload.get('timestamp')
    prefs['has_onboarded'] = True
    
    save_prefs(prefs)
    
    return jsonify({"ok": True, "data": prefs}), 200

