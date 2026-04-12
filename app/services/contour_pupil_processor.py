"""Adapter for routing wireless JPEG frames through existing contour/pupil CV logic."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, Tuple

import cv2
import numpy as np

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
        calibration_path: Optional[str] = None,
    ) -> None:
        self._screen_size_provider = screen_size_provider or self._default_screen_size_provider
        self._lock = threading.RLock()
        self._last_cursor_x = 0
        self._last_cursor_y = 0
        self._has_last_cursor = False
        self._calibration_path_requested = calibration_path
        self._gaze_tracker = None
        self._gaze_calibration_load_error: Optional[str] = None
        if calibration_path:
            try:
                from contour_gaze_tracker import ContourGazeTracker

                self._gaze_tracker = ContourGazeTracker(
                    enable_metrics=False,
                    calibration_path=calibration_path,
                )
                if not self._gaze_tracker.gaze_calibrator.is_fitted:
                    self._gaze_tracker = None
                    self._gaze_calibration_load_error = (
                        f"calibration not fitted (missing or invalid JSON): {calibration_path}"
                    )
            except Exception as exc:
                self._gaze_tracker = None
                self._gaze_calibration_load_error = str(exc)

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

    @staticmethod
    def _rescale_calibrated_px(
        sx: int,
        sy: int,
        screen_width: int,
        screen_height: int,
        cal_width: int,
        cal_height: int,
    ) -> Tuple[int, int]:
        """Map pixels from calibration resolution to current logical screen size."""
        cw = max(1, int(cal_width))
        ch = max(1, int(cal_height))
        sw = max(1, int(screen_width))
        sh = max(1, int(screen_height))
        # Single path: when sw==cw and sh==ch this is identity scale but still int-rounds and clamps.
        nx = int(round(float(sx) * sw / cw))
        ny = int(round(float(sy) * sh / ch))
        nx = max(0, min(sw - 1, nx))
        ny = max(0, min(sh - 1, ny))
        return nx, ny

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
                    "gaze_mapping": "none",
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

        diagnostics: Dict[str, Any] = {
            "stage": "contour_pupil",
            "detection_ok": bool(has_detection),
            "screen_width": screen_width,
            "screen_height": screen_height,
            "frame_width": frame_width,
            "frame_height": frame_height,
        }
        if self._calibration_path_requested:
            diagnostics["calibration_path"] = self._calibration_path_requested
        if self._gaze_calibration_load_error:
            diagnostics["calibration_warning"] = self._gaze_calibration_load_error

        if has_detection:
            x_frame = int(full_center[0])
            y_frame = int(full_center[1])
            gaze_mapping = "linear_frame"
            cursor_x: int
            cursor_y: int

            if self._gaze_tracker is not None:
                gaze = self._gaze_tracker.extract_gaze_numbers(full_center, None, frame.shape)
                if gaze and gaze.get("screen_px") is not None:
                    spx, spy = int(gaze["screen_px"][0]), int(gaze["screen_px"][1])
                    cal = self._gaze_tracker.gaze_calibrator
                    cursor_x, cursor_y = self._rescale_calibrated_px(
                        spx,
                        spy,
                        screen_width,
                        screen_height,
                        cal.screen_width,
                        cal.screen_height,
                    )
                    gaze_mapping = "calibrated_quadratic"
                    diagnostics["single_offset"] = gaze.get("single_offset")
                else:
                    cursor_x, cursor_y = self._map_to_screen(
                        x_frame=x_frame,
                        y_frame=y_frame,
                        frame_width=frame_width,
                        frame_height=frame_height,
                        screen_width=screen_width,
                        screen_height=screen_height,
                    )
            else:
                cursor_x, cursor_y = self._map_to_screen(
                    x_frame=x_frame,
                    y_frame=y_frame,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    screen_width=screen_width,
                    screen_height=screen_height,
                )

            self._remember_cursor(cursor_x, cursor_y)
            diagnostics.update(
                {
                    "reason": "detected",
                    "used_fallback": False,
                    "gaze_mapping": gaze_mapping,
                    "pupil_center": {"x": x_frame, "y": y_frame},
                }
            )
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
        diagnostics.update({"reason": reason, "used_fallback": True, "gaze_mapping": "none"})

        return {
            "ok": True,
            "cursor": {"x": cursor_x, "y": cursor_y, "confidence": 0.1},
            "diagnostics": diagnostics,
            "error": None,
        }
