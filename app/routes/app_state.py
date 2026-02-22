from __future__ import annotations

from flask import Blueprint, jsonify

from app.prefs_utils import load_prefs
from app import serial_connect
from app.services.runtime_context import runtime_store


app_state_bp = Blueprint("app_state", __name__, url_prefix="/app")


@app_state_bp.route("/bootstrap", methods=["GET"])
def bootstrap() -> tuple:
    prefs = load_prefs()
    state = runtime_store.get_state()

    esp_connected = bool(state.get("serial", {}).get("connected") or state.get("wireless", {}).get("connected"))
    if not esp_connected and prefs.get("has_onboarded"):
        known_port = prefs.get("last_serial_port")
        available_ports = [getattr(p, "device", "") for p in serial_connect.list_serial_ports()]
        if known_port and known_port in available_ports:
            esp_connected = True

    has_onboarded = bool(prefs.get("has_onboarded"))
    calibration_complete = bool(prefs.get("calibration_data"))

    if not has_onboarded:
        recommended_page = "welcome.html"
    elif esp_connected:
        recommended_page = "settings.html"
    else:
        recommended_page = "connect.html"

    active_mode = state.get("mode")
    if active_mode == "idle":
        active_mode = prefs.get("connection_method") or "wifi"

    payload = {
        "has_onboarded": has_onboarded,
        "esp_connected": esp_connected,
        "active_mode": active_mode,
        "calibration_complete": calibration_complete,
        "recommended_page": recommended_page,
    }
    return jsonify({"ok": True, "data": payload}), 200
