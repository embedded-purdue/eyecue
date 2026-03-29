from __future__ import annotations

from flask import Blueprint, jsonify

from app import serial_connect
from app.prefs_utils import load_prefs
from app.services.runtime_context import pipeline_controller


app_state_bp = Blueprint("app_state", __name__, url_prefix="/app")


@app_state_bp.route("/bootstrap", methods=["GET"])
def bootstrap() -> tuple:
    prefs = load_prefs()
    ports = serial_connect.list_serial_ports()
    runtime = pipeline_controller.get_state()
    payload = {
        "prefs": {
            "wifi_ssid": prefs.get("wifi_ssid", ""),
            "wifi_password": prefs.get("wifi_password", ""),
            "last_serial_port": prefs.get("last_serial_port", ""),
        },
        "serial_ports": [
            {
                "device": getattr(port, "device", ""),
                "description": getattr(port, "description", ""),
                "hwid": getattr(port, "hwid", ""),
            }
            for port in ports
        ],
        "runtime": runtime,
        "tracking_enabled": bool(runtime.get("tracking_enabled", False)),
    }
    return jsonify({"ok": True, "data": payload}), 200
