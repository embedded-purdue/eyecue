from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.runtime_context import runtime_store, wireless_video_service


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


def _parse_optional_int(name: str):
    value = request.form.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@ingest_bp.route("/wireless/frame", methods=["POST"])
def ingest_wireless_frame() -> tuple:
    frame_file = request.files.get("frame")
    if frame_file is None:
        return jsonify({"ok": False, "error": "frame file is required"}), 400

    frame_bytes = frame_file.read()
    if not frame_bytes:
        return jsonify({"ok": False, "error": "frame file is empty"}), 400

    device_id = request.form.get("device_id")
    if not wireless_video_service.is_processor_ready():
        status = wireless_video_service.get_processor_status()
        runtime_store.set_wireless_status(
            connected=False,
            device_id=device_id,
            last_error=status.get("cv_error") or "cv processor unavailable",
        )
        return jsonify({"ok": False, "error": "cv processor unavailable"}), 503

    try:
        metadata = {
            "device_id": device_id,
            "frame_ts_ms": _parse_optional_int("frame_ts_ms"),
            "seq": _parse_optional_int("seq"),
            "width": _parse_optional_int("width"),
            "height": _parse_optional_int("height"),
            "format": request.form.get("format") or "jpeg",
            "source_tag": request.form.get("source_tag"),
            "filename": frame_file.filename,
            "content_type": frame_file.content_type,
        }
        print(
            (
                "[TRACE][ingest.frame] received "
                f"device_id={device_id} seq={metadata.get('seq')} "
                f"frame_ts_ms={metadata.get('frame_ts_ms')} size={len(frame_bytes)}"
            ),
            flush=True,
        )
        result = wireless_video_service.run_frame_pipeline(frame_bytes, metadata)
        print(
            (
                "[TRACE][ingest.frame] pipeline_result "
                f"seq={metadata.get('seq')} ok={result.get('ok')} "
                f"cursor_published={result.get('cursor_published')} "
                f"detection_ok={result.get('detection_ok')} "
                f"used_fallback={result.get('used_fallback')} "
                f"latency_ms={result.get('latency_ms')} dropped={result.get('dropped')}"
            ),
            flush=True,
        )
        if not result.get("ok", False):
            raise RuntimeError(result.get("error") or "frame processing failed")
    except ValueError as exc:
        runtime_store.set_wireless_status(
            connected=False,
            device_id=device_id,
            last_error=str(exc),
        )
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - runtime guard
        runtime_store.set_wireless_status(
            connected=False,
            device_id=device_id,
            last_error=str(exc),
        )
        return jsonify({"ok": False, "error": "failed to process frame"}), 500

    runtime_store.set_wireless_status(connected=True, device_id=device_id)
    return jsonify({"ok": True}), 200
