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


@runtime_bp.route("/bypass", methods=["POST"])
def bypass_runtime() -> tuple:
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
            bypass=True,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    prefs = load_prefs()
    if ssid:
        prefs["wifi_ssid"] = ssid
    if password:
        prefs["wifi_password"] = password
    if serial_port:
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


# ── Calibration endpoints ──────────────────────────────────────────────

@runtime_bp.route("/calibrate/state", methods=["GET"])
def calibrate_state() -> tuple:
    return jsonify({"ok": True, "data": pipeline_controller.get_calibration_state()}), 200


@runtime_bp.route("/calibrate/start", methods=["POST"])
def calibrate_start() -> tuple:
    try:
        data = pipeline_controller.start_calibration()
        return jsonify({"ok": True, "data": data}), 200
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@runtime_bp.route("/calibrate/record", methods=["POST"])
def calibrate_record() -> tuple:
    body = request.get_json(silent=True) or {}
    point_index = body.get("point_index")
    screen_x = body.get("screen_x")
    screen_y = body.get("screen_y")

    if point_index is None or screen_x is None or screen_y is None:
        return jsonify({"ok": False, "error": "point_index, screen_x, screen_y are required"}), 400

    try:
        data = pipeline_controller.record_calibration_point(
            int(point_index), float(screen_x), float(screen_y)
        )
        return jsonify({"ok": True, "data": data}), 200
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@runtime_bp.route("/calibrate/finish", methods=["POST"])
def calibrate_finish() -> tuple:
    try:
        data = pipeline_controller.finish_calibration()
        return jsonify({"ok": True, "data": data}), 200
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@runtime_bp.route("/calibrate/cancel", methods=["POST"])
def calibrate_cancel() -> tuple:
    data = pipeline_controller.cancel_calibration()
    return jsonify({"ok": True, "data": data}), 200


@runtime_bp.route("/calibrate/quick", methods=["POST"])
def calibrate_quick() -> tuple:
    body = request.get_json(silent=True) or {}
    screen_x = body.get("screen_x")
    screen_y = body.get("screen_y")

    if screen_x is None or screen_y is None:
        return jsonify({"ok": False, "error": "screen_x, screen_y are required"}), 400

    try:
        data = pipeline_controller.quick_recalibrate(float(screen_x), float(screen_y))
        return jsonify({"ok": True, "data": data}), 200
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@runtime_bp.route("/gaze/current", methods=["GET"])
def current_gaze() -> tuple:
    """Return the latest raw gaze angles (for calibration recording)."""
    data = pipeline_controller.get_current_gaze()
    return jsonify({"ok": True, "data": data}), 200
