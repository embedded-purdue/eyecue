from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.prefs_utils import load_prefs
from app.services.runtime_context import runtime_store


internal_bp = Blueprint("internal", __name__, url_prefix="/internal")


def _is_local_request() -> bool:
    remote_addr = request.remote_addr
    if remote_addr in {"127.0.0.1", "::1", "localhost"}:
        return True
    return bool(remote_addr and remote_addr.endswith("127.0.0.1"))


@internal_bp.before_request
def restrict_to_localhost():
    if not _is_local_request():
        return jsonify({"ok": False, "error": "internal endpoint"}), 403
    return None


@internal_bp.route("/ingest/cursor", methods=["POST"])
def ingest_cursor() -> tuple:
    body = request.get_json(silent=True) or {}
    if "x" not in body or "y" not in body:
        return jsonify({"ok": False, "error": "x and y are required"}), 400
    try:
        sample = runtime_store.ingest_cursor_sample(body, default_source="serial")
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "data": sample}), 200


@internal_bp.route("/ingest/stats", methods=["POST"])
def ingest_stats() -> tuple:
    body = request.get_json(silent=True) or {}
    agent = str(body.get("agent") or "unknown")

    if agent == "cursor" and body.get("applied_sample"):
        sample = body.get("applied_sample")
        lag = body.get("queue_lag_ms")
        runtime_store.set_cursor_applied(sample, lag)

    runtime_store.set_agent_stats(agent, body)
    return jsonify({"ok": True}), 200


@internal_bp.route("/cursor/latest", methods=["GET"])
def cursor_latest() -> tuple:
    sample = runtime_store.get_latest_cursor()
    return jsonify({"ok": True, "data": sample}), 200


@internal_bp.route("/cursor/params", methods=["GET"])
def cursor_params() -> tuple:
    prefs = load_prefs()
    params = runtime_store.get_cursor_params(prefs)
    return jsonify({"ok": True, "data": params}), 200
