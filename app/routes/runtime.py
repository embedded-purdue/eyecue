from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.prefs_utils import load_prefs, save_prefs
from app.services.runtime_context import pipeline_controller


runtime_bp = Blueprint("runtime", __name__, url_prefix="/runtime")


@runtime_bp.route("/state", methods=["GET"])
def state() -> tuple:
    return jsonify({"ok": True, "data": pipeline_controller.get_state()}), 200


@runtime_bp.route("/connect", methods=["POST"])
def connect_runtime() -> tuple:
    body = request.get_json(silent=True) or {}
    serial_port = str(body.get("serial_port") or body.get("port") or "").strip()
    ssid = str(body.get("ssid") or "").strip()
    password = str(body.get("password") or "")
    baud = int(body.get("baud") or 115200)

    try:
        state = pipeline_controller.connect(
            ssid=ssid,
            password=password,
            serial_port=serial_port,
            baud=baud,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    prefs = load_prefs()
    prefs["wifi_ssid"] = ssid
    prefs["wifi_password"] = password
    prefs["last_serial_port"] = serial_port
    save_prefs(prefs)

    return jsonify({"ok": True, "data": state}), 200


@runtime_bp.route("/tracking", methods=["POST"])
def set_tracking() -> tuple:
    body = request.get_json(silent=True) or {}
    if "enabled" not in body:
        return jsonify({"ok": False, "error": "enabled is required"}), 400
    state = pipeline_controller.set_tracking(bool(body.get("enabled")))
    return jsonify({"ok": True, "data": state}), 200


@runtime_bp.route("/stop", methods=["POST"])
def stop_runtime() -> tuple:
    return jsonify({"ok": True, "data": pipeline_controller.stop()}), 200
