from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.config import ALLOWED_RUNTIME_MODES
from app.prefs_utils import DEFAULT_PREFS, load_prefs, save_prefs
from app.services.runtime_context import agent_supervisor, runtime_store


runtime_bp = Blueprint("runtime", __name__, url_prefix="/runtime")


@runtime_bp.route("/state", methods=["GET"])
def state() -> tuple:
    payload = runtime_store.get_state()
    payload["agents"] = agent_supervisor.status()
    return jsonify({"ok": True, "data": payload}), 200


@runtime_bp.route("/start", methods=["POST"])
def start_runtime() -> tuple:
    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode") or "serial").lower()
    port = body.get("port")
    ssid = body.get("ssid")
    password = body.get("password")
    baud = int(body.get("baud") or 115200)

    if mode not in ALLOWED_RUNTIME_MODES:
        return jsonify({"ok": False, "error": f"mode must be one of {sorted(ALLOWED_RUNTIME_MODES)}"}), 400

    try:
        state = agent_supervisor.start_runtime(
            mode=mode,
            port=port,
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
    for key in DEFAULT_PREFS.keys():
        prefs.setdefault(key, DEFAULT_PREFS[key])

    prefs["connection_method"] = mode
    if port:
        prefs["last_serial_port"] = str(port)
    if ssid is not None:
        prefs["wifi_ssid"] = str(ssid)
    if password is not None:
        prefs["wifi_password"] = str(password)

    save_prefs(prefs)

    state["agents"] = agent_supervisor.status()
    return jsonify({"ok": True, "data": state}), 200


@runtime_bp.route("/stop", methods=["POST"])
def stop_runtime() -> tuple:
    state = agent_supervisor.stop_runtime(clear=True)
    state["agents"] = agent_supervisor.status()
    return jsonify({"ok": True, "data": state}), 200
