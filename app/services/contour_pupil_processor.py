"""Adapter for routing wireless JPEG frames through existing contour/pupil CV logic."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, Tuple

import cv2
import numpy as np

from contour_gaze_tracker import ContourGazeTracker, map_gaze_angles_to_screen
from pupil_detector import detect_pupil_contour

try:
    import pyautogui
except Exception:  # pragma: no cover - optional runtime dependency
    pyautogui = None


DEFAULT_SCREEN_WIDTH = 1920
DEFAULT_SCREEN_HEIGHT = 1080


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


class ContourPupilFrameProcessor:
    """Frame processor that wraps existing `pupil_detector.detect_pupil_contour`."""

    name = "contour_pupil"

    def __init__(
        self,
        *,
        screen_size_provider: Optional[Callable[[], Tuple[int, int]]] = None,
    ) -> None:
        self._screen_size_provider = screen_size_provider or self._default_screen_size_provider
        self._lock = threading.RLock()
        self._last_cursor_x = 0
        self._last_cursor_y = 0
        self._has_last_cursor = False
        self._frame_count = 0
        self._smoothed_pupil_center: Optional[Tuple[int, int]] = None
        self._smoothing_alpha = 0.3
        self._gaze_tracker = ContourGazeTracker(enable_metrics=False, quiet=True)

    @staticmethod
    def _default_screen_size_provider() -> Tuple[int, int]:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available")
        width, height = pyautogui.size()
        return int(width), int(height)

    def _resolve_screen_size(self, metadata: Dict[str, Any]) -> Tuple[int, int]:
        try:
            width, height = self._screen_size_provider()
            if int(width) > 0 and int(height) > 0:
                return int(width), int(height)
        except Exception:
            pass

        width = _safe_int(metadata.get("width"))
        height = _safe_int(metadata.get("height"))
        if width and height and width > 0 and height > 0:
            return width, height

        return DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT

    @staticmethod
    def _decode_frame(frame_bytes: bytes) -> Optional[np.ndarray]:
        if not frame_bytes:
            return None
        decoded = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        return decoded

    @staticmethod
    def _map_to_screen(
        x_frame: int,
        y_frame: int,
        frame_width: int,
        frame_height: int,
        screen_width: int,
        screen_height: int,
    ) -> Tuple[int, int]:
        width = max(1, int(frame_width))
        height = max(1, int(frame_height))
        screen_w = max(1, int(screen_width))
        screen_h = max(1, int(screen_height))

        x = int(round((float(x_frame) / width) * screen_w))
        y = int(round((float(y_frame) / height) * screen_h))

        x = max(0, min(screen_w - 1, x))
        y = max(0, min(screen_h - 1, y))
        return x, y

    def _remember_cursor(self, x: int, y: int) -> None:
        with self._lock:
            self._last_cursor_x = int(x)
            self._last_cursor_y = int(y)
            self._has_last_cursor = True

    def _fallback_cursor(self, *, screen_width: int, screen_height: int, reason_prefix: str) -> Tuple[int, int, str]:
        with self._lock:
            if self._has_last_cursor:
                return self._last_cursor_x, self._last_cursor_y, f"{reason_prefix}_hold_last"

        x = max(0, int(screen_width) // 2)
        y = max(0, int(screen_height) // 2)
        self._remember_cursor(x, y)
        return x, y, f"{reason_prefix}_center"

    def process_frame(self, frame_bytes: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]:
        screen_width, screen_height = self._resolve_screen_size(metadata)

        frame = self._decode_frame(frame_bytes)
        if frame is None:
            cursor_x, cursor_y, reason = self._fallback_cursor(
                screen_width=screen_width,
                screen_height=screen_height,
                reason_prefix="decode_failed",
            )
            return {
                "ok": True,
                "cursor": {"x": cursor_x, "y": cursor_y, "confidence": 0.1},
                "diagnostics": {
                    "stage": "contour_pupil",
                    "reason": reason,
                    "detection_ok": False,
                    "used_fallback": True,
                    "screen_width": screen_width,
                    "screen_height": screen_height,
                },
                "error": None,
            }

        frame_height, frame_width = frame.shape[:2]

        try:
            full_center, _roi_center, bbox = detect_pupil_contour(frame)
        except Exception as exc:  # pragma: no cover - runtime guard
            return {
                "ok": False,
                "cursor": None,
                "diagnostics": {
                    "stage": "contour_pupil",
                    "reason": "detection_exception",
                    "detection_ok": False,
                    "used_fallback": False,
                    "screen_width": screen_width,
                    "screen_height": screen_height,
                    "frame_width": frame_width,
                    "frame_height": frame_height,
                },
                "error": str(exc),
            }

        has_detection = (
            isinstance(full_center, tuple)
            and len(full_center) >= 2
            and full_center[0] is not None
            and full_center[1] is not None
        )
        self._frame_count += 1

        if has_detection:
            raw_center = (int(full_center[0]), int(full_center[1]))
            if self._smoothed_pupil_center is None:
                self._smoothed_pupil_center = raw_center
            else:
                self._smoothed_pupil_center = (
                    int(
                        self._smoothing_alpha * raw_center[0]
                        + (1 - self._smoothing_alpha) * self._smoothed_pupil_center[0]
                    ),
                    int(
                        self._smoothing_alpha * raw_center[1]
                        + (1 - self._smoothing_alpha) * self._smoothed_pupil_center[1]
                    ),
                )
        elif self._frame_count % 10 == 0 and self._smoothed_pupil_center is not None:
            self._smoothed_pupil_center = None

        diagnostics: Dict[str, Any] = {
            "stage": "contour_pupil",
            "detection_ok": bool(has_detection),
            "screen_width": screen_width,
            "screen_height": screen_height,
            "frame_width": frame_width,
            "frame_height": frame_height,
        }

        if has_detection:
            stable_pupil_center = self._smoothed_pupil_center
            if stable_pupil_center is None:
                stable_pupil_center = (int(full_center[0]), int(full_center[1]))
            x_frame = int(stable_pupil_center[0])
            y_frame = int(stable_pupil_center[1])
            cursor_x: Optional[int] = None
            cursor_y: Optional[int] = None
            gaze_data: Optional[Dict[str, Any]] = None
            gaze_error: Optional[str] = None

            try:
                gaze_data = self._gaze_tracker.extract_gaze_numbers((x_frame, y_frame), _roi_center, frame.shape)
                if not gaze_data:
                    gaze_error = "gaze_data_unavailable"
                else:
                    single_angles = gaze_data.get("single_angles")
                    if isinstance(single_angles, (list, tuple)) and len(single_angles) >= 2:
                        cursor_x, cursor_y = map_gaze_angles_to_screen(
                            angle_h=float(single_angles[0]),
                            angle_v=float(single_angles[1]),
                            screen_width=screen_width,
                            screen_height=screen_height,
                        )
                    else:
                        gaze_error = "gaze_angles_unavailable"
            except Exception as exc:  # pragma: no cover - runtime guard
                gaze_error = f"gaze_exception: {exc}"

            if cursor_x is None or cursor_y is None:
                cursor_x, cursor_y = self._map_to_screen(
                    x_frame=x_frame,
                    y_frame=y_frame,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    screen_width=screen_width,
                    screen_height=screen_height,
                )
                diagnostics["mapping_source"] = "frame_linear_fallback"
                diagnostics["reason"] = (
                    "detected_linear_fallback_gaze_unavailable"
                    if gaze_error in ("gaze_data_unavailable", "gaze_angles_unavailable")
                    else "detected_linear_fallback_gaze_error"
                )
                diagnostics["used_fallback"] = True
                if gaze_error:
                    diagnostics["gaze_error"] = gaze_error
            else:
                diagnostics["mapping_source"] = "gaze_angles_cursorcontroller"
                diagnostics["reason"] = "detected_gaze_mapped"
                diagnostics["used_fallback"] = False

            self._remember_cursor(cursor_x, cursor_y)

            diagnostics.update(
                {
                    "pupil_center": {"x": x_frame, "y": y_frame},
                }
            )
            if isinstance(gaze_data, dict):
                single_angles = gaze_data.get("single_angles")
                single_offset = gaze_data.get("single_offset")
                single_gaze_vector = gaze_data.get("single_gaze_vector")
                if isinstance(single_angles, (list, tuple)) and len(single_angles) >= 2:
                    diagnostics["single_angles"] = [float(single_angles[0]), float(single_angles[1])]
                if isinstance(single_offset, (list, tuple)) and len(single_offset) >= 2:
                    diagnostics["single_offset"] = [float(single_offset[0]), float(single_offset[1])]
                if isinstance(single_gaze_vector, (list, tuple)) and len(single_gaze_vector) >= 3:
                    diagnostics["single_gaze_vector"] = [
                        float(single_gaze_vector[0]),
                        float(single_gaze_vector[1]),
                        float(single_gaze_vector[2]),
                    ]

            if isinstance(bbox, tuple) and len(bbox) >= 2:
                diagnostics["bbox"] = {"w": int(bbox[0]), "h": int(bbox[1])}

            return {
                "ok": True,
                "cursor": {"x": cursor_x, "y": cursor_y, "confidence": 0.8},
                "diagnostics": diagnostics,
                "error": None,
            }

        cursor_x, cursor_y, reason = self._fallback_cursor(
            screen_width=screen_width,
            screen_height=screen_height,
            reason_prefix="no_detection",
        )
        diagnostics.update({"reason": reason, "used_fallback": True})

        return {
            "ok": True,
            "cursor": {"x": cursor_x, "y": cursor_y, "confidence": 0.1},
            "diagnostics": diagnostics,
            "error": None,
        }
