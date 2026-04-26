"""Adapter for routing wireless JPEG frames through existing contour/pupil CV logic."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np
import cv2

from contour_gaze_tracker import (
    DEFAULT_PROJECTION_HALF_FOV_DEG,
    ContourGazeTracker,
    map_gaze_angles_to_screen,
)
from app.config import (
    EYE_BASELINE_CONFIDENCE_FLOOR,
    EYE_BASELINE_DEADZONE_X,
    EYE_BASELINE_DEADZONE_Y,
    EYE_BASELINE_GAIN_X,
    EYE_BASELINE_GAIN_Y,
    EYE_BASELINE_SAMPLES,
)
from pupil_detector import OneEuroFilter2D, PupilTracker

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
    """Frame processor that routes JPEG frames through the stateful contour pupil tracker."""

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
        self._pupil_tracker = PupilTracker()
        self._smoother = OneEuroFilter2D()
        self._confidence_floor = 0.30
        self._baseline_confidence_floor = max(0.0, float(EYE_BASELINE_CONFIDENCE_FLOOR))
        self._baseline_required_samples = max(1, int(EYE_BASELINE_SAMPLES))
        self._baseline_deadzone_x = max(0.0, float(EYE_BASELINE_DEADZONE_X))
        self._baseline_deadzone_y = max(0.0, float(EYE_BASELINE_DEADZONE_Y))
        self._baseline_gain_x = max(0.0, float(EYE_BASELINE_GAIN_X))
        self._baseline_gain_y = max(0.0, float(EYE_BASELINE_GAIN_Y))
        self._baseline_samples: list[Tuple[int, int]] = []
        self._baseline_pupil_center: Optional[Tuple[float, float]] = None
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

    @staticmethod
    def _apply_deadzone(value: float, deadzone: float) -> float:
        if abs(value) <= deadzone:
            return 0.0
        if value > 0:
            return value - deadzone
        return value + deadzone

    def _baseline_ready(self) -> bool:
        return self._baseline_pupil_center is not None

    def _maybe_collect_baseline_sample(
        self,
        pupil_center: Tuple[int, int],
        *,
        confidence: float,
        tracker_source: str,
    ) -> None:
        if self._baseline_ready():
            return
        if tracker_source == "hold":
            return
        if confidence < self._baseline_confidence_floor:
            return

        self._baseline_samples.append((int(pupil_center[0]), int(pupil_center[1])))
        if len(self._baseline_samples) >= self._baseline_required_samples:
            xs = [sample[0] for sample in self._baseline_samples]
            ys = [sample[1] for sample in self._baseline_samples]
            self._baseline_pupil_center = (float(np.median(xs)), float(np.median(ys)))

    def _add_baseline_diagnostics(
        self,
        diagnostics: Dict[str, Any],
        *,
        baseline_offset: Optional[Tuple[float, float]] = None,
    ) -> None:
        diagnostics["baseline_ready"] = self._baseline_ready()
        diagnostics["baseline_sample_count"] = len(self._baseline_samples)
        if self._baseline_pupil_center is None:
            diagnostics["baseline_pupil_center"] = None
        else:
            diagnostics["baseline_pupil_center"] = {
                "x": float(self._baseline_pupil_center[0]),
                "y": float(self._baseline_pupil_center[1]),
            }

        diagnostics["baseline_offset"] = None
        if baseline_offset is not None:
            diagnostics["baseline_offset"] = {
                "x": float(baseline_offset[0]),
                "y": float(baseline_offset[1]),
            }

    def _map_with_baseline(
        self,
        *,
        pupil_center: Tuple[int, int],
        frame_width: int,
        frame_height: int,
        screen_width: int,
        screen_height: int,
    ) -> Optional[Tuple[int, int, Tuple[float, float]]]:
        if self._baseline_pupil_center is None:
            return None

        frame_w = max(1, int(frame_width))
        frame_h = max(1, int(frame_height))
        screen_w = max(1, int(screen_width))
        screen_h = max(1, int(screen_height))

        raw_offset_x = (float(pupil_center[0]) - self._baseline_pupil_center[0]) / float(frame_w)
        raw_offset_y = (float(pupil_center[1]) - self._baseline_pupil_center[1]) / float(frame_h)
        offset_x = self._apply_deadzone(raw_offset_x, self._baseline_deadzone_x)
        offset_y = self._apply_deadzone(raw_offset_y, self._baseline_deadzone_y)

        cursor_x = int(round((screen_w / 2.0) + (offset_x * self._baseline_gain_x * screen_w)))
        cursor_y = int(round((screen_h / 2.0) + (offset_y * self._baseline_gain_y * screen_h)))

        cursor_x = max(0, min(screen_w - 1, cursor_x))
        cursor_y = max(0, min(screen_h - 1, cursor_y))
        return cursor_x, cursor_y, (offset_x, offset_y)

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
            diagnostics = {
                "stage": "contour_pupil",
                "reason": reason,
                "detection_ok": False,
                "used_fallback": True,
                "screen_width": screen_width,
                "screen_height": screen_height,
                "frame_mirrored": False,
            }
            self._add_baseline_diagnostics(diagnostics)
            return {
                "ok": True,
                "cursor": {"x": cursor_x, "y": cursor_y, "confidence": 0.1},
                "diagnostics": diagnostics,
                "error": None,
            }

        frame_height, frame_width = frame.shape[:2]

        # mirror horizontally — camera faces the eye so left/right are reversed
        frame = cv2.flip(frame, 1)

        try:
            track = self._pupil_tracker.update(frame)
            full_center = track['center']
            bbox = track['bbox']
            confidence = float(track['confidence'])
            tracker_source = str(track.get('source') or 'unknown')
            _roi_center = None
        except Exception as exc:  # pragma: no cover - runtime guard
            diagnostics = {
                "stage": "contour_pupil",
                "reason": "detection_exception",
                "detection_ok": False,
                "used_fallback": False,
                "screen_width": screen_width,
                "screen_height": screen_height,
                "frame_width": frame_width,
                "frame_height": frame_height,
                "frame_mirrored": True,
            }
            self._add_baseline_diagnostics(diagnostics)
            return {
                "ok": False,
                "cursor": None,
                "diagnostics": diagnostics,
                "error": str(exc),
            }

        has_detection = (
            isinstance(full_center, tuple)
            and len(full_center) >= 2
            and full_center[0] is not None
            and full_center[1] is not None
        )
        self._frame_count += 1
        raw_pupil_center = None
        if has_detection:
            raw_pupil_center = (int(full_center[0]), int(full_center[1]))

        if has_detection and confidence >= self._confidence_floor:
            sx, sy = self._smoother(raw_pupil_center)
            self._smoothed_pupil_center = (int(round(sx)), int(round(sy)))
        elif tracker_source == "hold" and self._smoothed_pupil_center is not None:
            # Tracker hold: preserve last smoothed position for a short dropout.
            pass
        else:
            # True miss or weak fresh candidate: reset so re-acquire does not snap.
            self._smoother.reset()
            self._smoothed_pupil_center = None

        usable_detection = self._smoothed_pupil_center is not None and (
            (has_detection and confidence >= self._confidence_floor) or tracker_source == "hold"
        )

        diagnostics: Dict[str, Any] = {
            "stage": "contour_pupil",
            "detection_ok": bool(usable_detection),
            "confidence": confidence,
            "tracker_source": tracker_source,
            "projection_half_fov_deg": DEFAULT_PROJECTION_HALF_FOV_DEG,
            "screen_width": screen_width,
            "screen_height": screen_height,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "frame_mirrored": True,
        }
        if raw_pupil_center is not None:
            diagnostics["raw_pupil_center"] = {"x": raw_pupil_center[0], "y": raw_pupil_center[1]}
        self._add_baseline_diagnostics(diagnostics)

        if usable_detection:
            stable_pupil_center = self._smoothed_pupil_center
            x_frame = int(stable_pupil_center[0])
            y_frame = int(stable_pupil_center[1])
            cursor_x: Optional[int] = None
            cursor_y: Optional[int] = None
            gaze_data: Optional[Dict[str, Any]] = None
            gaze_error: Optional[str] = None
            baseline_offset: Optional[Tuple[float, float]] = None

            baseline_sample_center = raw_pupil_center if raw_pupil_center is not None else (x_frame, y_frame)
            self._maybe_collect_baseline_sample(
                baseline_sample_center,
                confidence=confidence,
                tracker_source=tracker_source,
            )
            self._add_baseline_diagnostics(diagnostics)

            diagnostics.update(
                {
                    "pupil_center": {"x": x_frame, "y": y_frame},
                    "smoothed_pupil_center": {"x": x_frame, "y": y_frame},
                }
            )

            if not self._baseline_ready():
                cursor_x, cursor_y, reason = self._fallback_cursor(
                    screen_width=screen_width,
                    screen_height=screen_height,
                    reason_prefix="baseline_collecting",
                )
                diagnostics.update(
                    {
                        "mapping_source": "baseline_collecting",
                        "reason": "baseline_collecting",
                        "fallback_reason": reason,
                        "used_fallback": True,
                    }
                )

                if isinstance(bbox, tuple) and len(bbox) >= 2:
                    diagnostics["bbox"] = {"w": int(bbox[0]), "h": int(bbox[1])}

                return {
                    "ok": True,
                    "cursor": {"x": cursor_x, "y": cursor_y, "confidence": 0.2},
                    "diagnostics": diagnostics,
                    "error": None,
                }

            try:
                baseline_result = self._map_with_baseline(
                    pupil_center=(x_frame, y_frame),
                    frame_width=frame_width,
                    frame_height=frame_height,
                    screen_width=screen_width,
                    screen_height=screen_height,
                )
                if baseline_result is not None:
                    cursor_x, cursor_y, baseline_offset = baseline_result
            except Exception as exc:  # pragma: no cover - runtime guard
                gaze_error = f"baseline_exception: {exc}"

            if cursor_x is None or cursor_y is None:
                try:
                    gaze_data = self._gaze_tracker.extract_gaze_numbers((x_frame, y_frame), _roi_center, frame.shape)
                    if not gaze_data:
                        gaze_error = gaze_error or "gaze_data_unavailable"
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
                            gaze_error = gaze_error or "gaze_angles_unavailable"
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
            elif baseline_offset is not None:
                diagnostics["mapping_source"] = "neutral_baseline"
                diagnostics["reason"] = "detected_baseline_mapped"
                diagnostics["used_fallback"] = False
            else:
                diagnostics["mapping_source"] = "gaze_angles_cursorcontroller"
                diagnostics["reason"] = "detected_gaze_mapped"
                diagnostics["used_fallback"] = False

            self._add_baseline_diagnostics(diagnostics, baseline_offset=baseline_offset)

            self._remember_cursor(cursor_x, cursor_y)
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
                "cursor": {"x": cursor_x, "y": cursor_y, "confidence": float(confidence)},
                "diagnostics": diagnostics,
                "error": None,
            }

        reason_prefix = "low_confidence" if has_detection else "no_detection"
        cursor_x, cursor_y, reason = self._fallback_cursor(
            screen_width=screen_width,
            screen_height=screen_height,
            reason_prefix=reason_prefix,
        )
        diagnostics.update({"reason": reason, "used_fallback": True})

        return {
            "ok": True,
            "cursor": {"x": cursor_x, "y": cursor_y, "confidence": 0.1},
            "diagnostics": diagnostics,
            "error": None,
        }
