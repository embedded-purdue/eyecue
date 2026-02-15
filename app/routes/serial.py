from flask import Blueprint, request, jsonify

from prefs_utils import load_prefs, save_prefs, DEFAULT_PREFS
from services.serial_manager import serial_manager

serial_bp = Blueprint('serial', __name__, url_prefix='/serial')

@serial_bp.route('/ports', methods=["GET"])
def ports():
    return jsonify({"ok": True, "data": serial_manager.list_ports()}), 200


@serial_bp.route('/connect', methods=["POST"])
def connect():
    payload = request.get_json(silent=True) or {}
    port = payload.get("port")
    ssid = payload.get("ssid")
    password = payload.get("password")
    baud = payload.get("baud", 115200)

    if not port or not ssid or not password:
        return jsonify({"ok": False, "error": "port, ssid, and password are required"}), 400

    try:
        serial_manager.connect(port=port, ssid=ssid, password=password, baud=int(baud))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    prefs = load_prefs()
    prefs["wifi_ssid"] = ssid
    prefs["wifi_password"] = password
    prefs["last_serial_port"] = port
    prefs["connection_method"] = "serial"
    for key in DEFAULT_PREFS.keys():
        prefs.setdefault(key, DEFAULT_PREFS[key])
    save_prefs(prefs)

    return jsonify({"ok": True, "data": {"connected": True, "port": port}}), 200


@serial_bp.route('/disconnect', methods=["POST"])
def disconnect():
    serial_manager.disconnect()
    return jsonify({"ok": True}), 200


@serial_bp.route('/status', methods=["GET"])
def status():
    return jsonify({"ok": True, "data": serial_manager.status()}), 200
