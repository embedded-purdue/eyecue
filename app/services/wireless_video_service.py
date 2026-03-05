"""Wireless video ingest pipeline with pluggable frame processor."""

from __future__ import annotations

import copy
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Protocol

from app.config import WIRELESS_VIDEO_BUFFER_MAX, WIRELESS_VIDEO_MAX_FRAME_BYTES
from app.services.runtime_store import RuntimeStore, now_ms


class FrameProcessor(Protocol):
    def process_frame(self, frame_bytes: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process one frame and optionally return cursor output."""


class StubFrameProcessor:
    """Default placeholder processor.

    This intentionally does not run CV. It only validates that frame bytes exist.
    """

    def process_frame(self, frame_bytes: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]:
        if not frame_bytes:
            return {
                "ok": False,
                "cursor": None,
                "diagnostics": {"stage": "stub", "reason": "empty_frame"},
                "error": "empty frame",
            }

        return {
            "ok": True,
            "cursor": None,
            "diagnostics": {"stage": "stub", "reason": "not_implemented"},
            "error": None,
        }


class WirelessVideoService:
    def __init__(
        self,
        runtime_store: RuntimeStore,
        *,
        processor: Optional[FrameProcessor] = None,
        processor_name: Optional[str] = None,
        processor_ready: bool = True,
        processor_error: Optional[str] = None,
        frame_buffer_max: int = WIRELESS_VIDEO_BUFFER_MAX,
    ) -> None:
        self._runtime_store = runtime_store
        self._processor: FrameProcessor = processor or StubFrameProcessor()
        self._lock = threading.RLock()
        self._frames: Deque[Dict[str, Any]] = deque(maxlen=max(1, frame_buffer_max))
        self._results: Deque[Dict[str, Any]] = deque(maxlen=max(1, frame_buffer_max))

        self._processor_name = processor_name or getattr(self._processor, "name", type(self._processor).__name__)
        self._processor_ready = bool(processor_ready)
        self._processor_error = processor_error
        self._sync_processor_status()

    def _sync_processor_status(self) -> None:
        self._runtime_store.set_wireless_video_processor_status(
            processor_name=self._processor_name,
            cv_ready=self._processor_ready,
            cv_error=self._processor_error,
        )

    def set_processor(self, processor: FrameProcessor, *, processor_name: Optional[str] = None) -> None:
        with self._lock:
            self._processor = processor
            self._processor_name = processor_name or getattr(processor, "name", type(processor).__name__)
            self._processor_ready = True
            self._processor_error = None
            self._sync_processor_status()

    def set_processor_availability(
        self,
        *,
        ready: bool,
        error: Optional[str] = None,
        processor_name: Optional[str] = None,
    ) -> None:
        with self._lock:
            if processor_name:
                self._processor_name = processor_name
            self._processor_ready = bool(ready)
            self._processor_error = error
            self._sync_processor_status()

    def is_processor_ready(self) -> bool:
        with self._lock:
            return self._processor_ready

    def get_processor_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "processor_name": self._processor_name,
                "cv_ready": self._processor_ready,
                "cv_error": self._processor_error,
            }

    def get_debug_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "processor": self.get_processor_status(),
                "frames": copy.deepcopy(list(self._frames)),
                "results": copy.deepcopy(list(self._results)),
            }

    def run_frame_pipeline(self, frame_bytes: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]:
        if not frame_bytes:
            raise ValueError("frame is required")
        if len(frame_bytes) > WIRELESS_VIDEO_MAX_FRAME_BYTES:
            raise ValueError(f"frame exceeds max size of {WIRELESS_VIDEO_MAX_FRAME_BYTES} bytes")

        if not self.is_processor_ready():
            raise RuntimeError(self._processor_error or "cv processor unavailable")

        started = time.perf_counter()
        frame_ts_ms = int(metadata.get("frame_ts_ms") or now_ms())
        seq = metadata.get("seq")
        dropped = False

        with self._lock:
            dropped = len(self._frames) == self._frames.maxlen
            frame_entry = {
                "received_ts_ms": now_ms(),
                "frame_ts_ms": frame_ts_ms,
                "seq": seq,
                "device_id": metadata.get("device_id"),
                "width": metadata.get("width"),
                "height": metadata.get("height"),
                "format": metadata.get("format") or "jpeg",
                "source_tag": metadata.get("source_tag"),
                "size_bytes": len(frame_bytes),
                "bytes": frame_bytes,
            }
            self._frames.append(frame_entry)
            self._runtime_store.record_wireless_frame_ingest(
                {
                    "frame_ts_ms": frame_ts_ms,
                    "buffer_size": len(self._frames),
                }
            )

        cursor_published = False
        processing_error: Optional[str] = None
        diagnostics: Dict[str, Any] = {}

        try:
            result = self._processor.process_frame(frame_bytes, metadata) or {}
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            result = {
                "ok": False,
                "cursor": None,
                "diagnostics": {"stage": "processor", "reason": "exception"},
                "error": str(exc),
            }

        if not result.get("ok", False):
            processing_error = str(result.get("error") or "frame processing failed")
        diagnostics = result.get("diagnostics") or {}

        detection_ok = bool(result.get("detection_ok", diagnostics.get("detection_ok", False)))
        used_fallback = bool(result.get("used_fallback", diagnostics.get("used_fallback", False)))

        cursor = result.get("cursor")
        if cursor and isinstance(cursor, dict) and "x" in cursor and "y" in cursor:
            ingest_ts_ms = now_ms()
            sample_payload: Dict[str, Any] = {
                "x": cursor.get("x"),
                "y": cursor.get("y"),
                "ts_ms": ingest_ts_ms,
                "seq": seq,
                "source": "wireless",
                "raw": {
                    "pipeline": "wireless_video",
                    "device_id": metadata.get("device_id"),
                    "frame_ts_ms": frame_ts_ms,
                    "ingest_ts_ms": ingest_ts_ms,
                    "diagnostics": diagnostics,
                },
            }
            if "confidence" in cursor:
                sample_payload["confidence"] = cursor.get("confidence")

            skew_ms = ingest_ts_ms - frame_ts_ms
            print(
                (
                    "[TRACE][wireless_video] publish_cursor "
                    f"seq={seq} frame_ts_ms={frame_ts_ms} ingest_ts_ms={ingest_ts_ms} "
                    f"skew_ms={skew_ms} x={sample_payload.get('x')} "
                    f"y={sample_payload.get('y')} confidence={sample_payload.get('confidence')} "
                    f"detection_ok={detection_ok} fallback={used_fallback}"
                ),
                flush=True,
            )
            self._runtime_store.ingest_cursor_sample(sample_payload, default_source="wireless")
            cursor_published = True

        latency_ms = int((time.perf_counter() - started) * 1000)
        result_entry = {
            "processed_ts_ms": now_ms(),
            "frame_ts_ms": frame_ts_ms,
            "seq": seq,
            "device_id": metadata.get("device_id"),
            "ok": bool(result.get("ok", False)),
            "dropped": dropped,
            "error": processing_error,
            "diagnostics": diagnostics,
            "detection_ok": detection_ok,
            "used_fallback": used_fallback,
            "cursor_published": cursor_published,
            "latency_ms": latency_ms,
        }

        with self._lock:
            self._results.append(result_entry)
            self._runtime_store.record_wireless_frame_result(
                {
                    "processed_ts_ms": result_entry["processed_ts_ms"],
                    "latency_ms": latency_ms,
                    "error": processing_error,
                    "dropped": dropped,
                    "detection_ok": detection_ok,
                    "used_fallback": used_fallback,
                    "cursor_published": cursor_published,
                    "buffer_size": len(self._frames),
                }
            )

        return {
            "ok": processing_error is None,
            "error": processing_error,
            "detection_ok": detection_ok,
            "used_fallback": used_fallback,
            "cursor_published": cursor_published,
            "latency_ms": latency_ms,
            "dropped": dropped,
        }
