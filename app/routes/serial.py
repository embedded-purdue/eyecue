from __future__ import annotations

from flask import Blueprint, jsonify, request

from app import serial_connect
from app.prefs_utils import DEFAULT_PREFS, load_prefs, save_prefs
from app.services.runtime_context import agent_supervisor, runtime_store


serial_bp = Blueprint("serial", __name__, url_prefix="/serial")


@serial_bp.route("/ports", methods=["GET"])
def ports() -> tuple:
    ports = serial_connect.list_serial_ports()
    payload = [
        {
            "device": getattr(port, "device", ""),
            "description": getattr(port, "description", ""),
            "hwid": getattr(port, "hwid", ""),
        }
        for port in ports
    ]
    return jsonify({"ok": True, "data": payload}), 200


@serial_bp.route("/connect", methods=["POST"])
def connect() -> tuple:
    """Compatibility shim: forwards to runtime start."""
    body = request.get_json(silent=True) or {}
    port = body.get("port")
    ssid = body.get("ssid")
    password = body.get("password")
    baud = int(body.get("baud") or serial_connect.BAUD)

    if not port:
        return jsonify({"ok": False, "error": "port is required"}), 400

    try:
        state = agent_supervisor.start_runtime(
            mode="serial",
            port=str(port),
            ssid=ssid,
            password=password,
            baud=baud,
        )
    except ValueError as exc:
        runtime_store.set_last_error(str(exc))
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        runtime_store.set_last_error(str(exc))
        return jsonify({"ok": False, "error": str(exc)}), 500

    prefs = load_prefs()
    for key in DEFAULT_PREFS:
        prefs.setdefault(key, DEFAULT_PREFS[key])
    prefs["connection_method"] = "serial"
    prefs["last_serial_port"] = str(port)
    if ssid is not None:
        prefs["wifi_ssid"] = str(ssid)
    if password is not None:
        prefs["wifi_password"] = str(password)
    save_prefs(prefs)

    return jsonify({"ok": True, "data": state}), 200


@serial_bp.route("/disconnect", methods=["POST"])
def disconnect() -> tuple:
    """Compatibility shim: stops the serial agent only."""
    agent_supervisor.stop_serial_agent()
    state = runtime_store.get_state()
    return jsonify({"ok": True, "data": state}), 200


@serial_bp.route("/status", methods=["GET"])
def status() -> tuple:
    state = runtime_store.get_state()
    prefs = load_prefs()
    serial_state = state.get("serial", {})
    wireless_state = state.get("wireless", {})
    data = {
        "connected": bool(serial_state.get("connected")),
        "port": serial_state.get("port"),
        "baud_rate": serial_state.get("baud"),
        "last_error": serial_state.get("last_error"),
        "wifi_connected": bool(wireless_state.get("connected")),
        "wifi_ssid": prefs.get("wifi_ssid") or None,
        "wifi_ip": None,
        "camera_ready": state.get("connected", False),
        "active_source": state.get("active_source"),
    }
    return jsonify({"ok": True, "data": data}), 200
