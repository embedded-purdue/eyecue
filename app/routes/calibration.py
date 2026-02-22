from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.runtime_context import calibration_service


calibration_bp = Blueprint("calibration", __name__, url_prefix="/calibration")


@calibration_bp.route("/session", methods=["GET"])
def get_session() -> tuple:
    session = calibration_service.get_session()
    return jsonify({"ok": True, "data": session}), 200


@calibration_bp.route("/session/start", methods=["POST"])
def start_session() -> tuple:
    body = request.get_json(silent=True) or {}
    total_nodes = int(body.get("total_nodes") or 9)
    node_order = body.get("node_order")

    session = calibration_service.start_session(total_nodes=total_nodes, node_order=node_order)
    return jsonify({"ok": True, "data": session}), 200


@calibration_bp.route("/session/node", methods=["POST"])
def record_node() -> tuple:
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    node_index = body.get("node_index")
    if session_id is None or node_index is None:
        return jsonify({"ok": False, "error": "session_id and node_index are required"}), 400

    try:
        session = calibration_service.record_node(
            session_id=str(session_id),
            node_index=int(node_index),
            data=body.get("data"),
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": True, "data": session}), 200


@calibration_bp.route("/session/complete", methods=["POST"])
def complete_session() -> tuple:
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    if session_id is None:
        return jsonify({"ok": False, "error": "session_id is required"}), 400

    try:
        session = calibration_service.complete_session(
            session_id=str(session_id),
            calibration_data=body.get("calibration_data"),
            timestamp=body.get("timestamp"),
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": True, "data": session}), 200
