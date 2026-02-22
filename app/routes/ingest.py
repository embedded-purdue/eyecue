from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.runtime_context import runtime_store


ingest_bp = Blueprint("ingest", __name__, url_prefix="/ingest")


@ingest_bp.route("/wireless/cursor", methods=["POST"])
def ingest_wireless_cursor() -> tuple:
    body = request.get_json(silent=True) or {}
    if "x" not in body or "y" not in body:
        return jsonify({"ok": False, "error": "x and y are required"}), 400

    payload = dict(body)
    payload["source"] = "wireless"

    try:
        sample = runtime_store.ingest_cursor_sample(payload, default_source="wireless")
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    device_id = body.get("device_id")
    runtime_store.set_wireless_status(connected=True, device_id=device_id)
    return jsonify({"ok": True, "data": sample}), 200


@ingest_bp.route("/wireless/stats", methods=["POST"])
def ingest_wireless_stats() -> tuple:
    body = request.get_json(silent=True) or {}
    payload = dict(body)
    payload.setdefault("agent", "wireless")
    payload.setdefault("connected", True)
    runtime_store.set_agent_stats("wireless", payload)
    runtime_store.set_wireless_status(
        connected=bool(payload.get("connected", True)),
        device_id=payload.get("device_id"),
        last_error=payload.get("last_error"),
    )
    return jsonify({"ok": True}), 200
