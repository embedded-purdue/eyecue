"""Calibration service — stores reference gaze angles and computes affine mapping."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# 5-point calibration layout (percentage of screen)
CALIBRATION_POINTS = [
    (0.50, 0.50),  # center
    (0.05, 0.05),  # top-left
    (0.95, 0.05),  # top-right
    (0.05, 0.95),  # bottom-left
    (0.95, 0.95),  # bottom-right
]

PREFS_KEY = "calibration_data"


class CalibrationState:
    """Manages the calibration flow and stores the affine transform."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active = False
        self._point_index = 0
        # recorded pairs: list of (angle_h, angle_v, screen_x, screen_y)
        self._recorded: List[Tuple[float, float, float, float]] = []
        # affine transform matrices (2x3) — None until calibrated
        self._transform: Optional[np.ndarray] = None
        self._calibrated = False

    @property
    def is_calibrated(self) -> bool:
        with self._lock:
            return self._calibrated

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def start(self) -> Dict[str, Any]:
        """Begin a new calibration session."""
        with self._lock:
            self._active = True
            self._point_index = 0
            self._recorded = []
            return self._snapshot()

    def cancel(self) -> Dict[str, Any]:
        """Cancel the current calibration session."""
        with self._lock:
            self._active = False
            self._point_index = 0
            self._recorded = []
            return self._snapshot()

    def record_point(
        self, point_index: int, angle_h: float, angle_v: float,
        screen_x: float, screen_y: float
    ) -> Dict[str, Any]:
        """Record a gaze angle at a known screen position."""
        with self._lock:
            if not self._active:
                raise ValueError("Calibration not active")
            if point_index != self._point_index:
                raise ValueError(
                    f"Expected point {self._point_index}, got {point_index}"
                )
            self._recorded.append((
                float(angle_h), float(angle_v),
                float(screen_x), float(screen_y),
            ))
            self._point_index += 1
            return self._snapshot()

    def finish(self) -> Dict[str, Any]:
        """Compute the affine transform from recorded points."""
        with self._lock:
            if len(self._recorded) < 3:
                raise ValueError(
                    f"Need at least 3 points, have {len(self._recorded)}"
                )
            self._compute_transform()
            self._active = False
            return self._snapshot()

    def quick_recalibrate(self, angle_h: float, angle_v: float,
                          screen_x: float, screen_y: float) -> Dict[str, Any]:
        """Shift the existing calibration so (angle_h, angle_v) maps to (screen_x, screen_y).

        This adjusts for drift without redoing the full calibration.
        """
        with self._lock:
            if not self._calibrated or self._transform is None:
                raise ValueError("No existing calibration to adjust")

            # compute where the current angles would map
            current_x, current_y = self._apply_transform(angle_h, angle_v)

            # shift the translation component of the affine transform
            dx = screen_x - current_x
            dy = screen_y - current_y
            self._transform[0, 2] += dx
            self._transform[1, 2] += dy

            return self._snapshot()

    def apply(self, angle_h: float, angle_v: float) -> Optional[Tuple[int, int]]:
        """Map gaze angles to screen coordinates using the calibrated transform."""
        with self._lock:
            if not self._calibrated or self._transform is None:
                return None
            x, y = self._apply_transform(angle_h, angle_v)
            return int(round(x)), int(round(y))

    def _apply_transform(self, angle_h: float, angle_v: float) -> Tuple[float, float]:
        """Raw affine transform application (must hold lock)."""
        src = np.array([angle_h, angle_v, 1.0])
        x = float(self._transform[0] @ src)
        y = float(self._transform[1] @ src)
        return x, y

    def _compute_transform(self) -> None:
        """Fit an affine transform from gaze angles to screen coords using least squares."""
        n = len(self._recorded)
        # build matrices: A * params = B
        # where A is [angle_h, angle_v, 1] and B is [screen_x, screen_y]
        A = np.zeros((n, 3))
        Bx = np.zeros(n)
        By = np.zeros(n)

        for i, (ah, av, sx, sy) in enumerate(self._recorded):
            A[i] = [ah, av, 1.0]
            Bx[i] = sx
            By[i] = sy

        # least squares solve: A @ params_x = Bx, A @ params_y = By
        params_x, _, _, _ = np.linalg.lstsq(A, Bx, rcond=None)
        params_y, _, _, _ = np.linalg.lstsq(A, By, rcond=None)

        self._transform = np.array([params_x, params_y])
        self._calibrated = True

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "active": self._active,
            "calibrated": self._calibrated,
            "point_index": self._point_index,
            "total_points": len(CALIBRATION_POINTS),
            "recorded_count": len(self._recorded),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for persistence."""
        with self._lock:
            result = self._snapshot()
            if self._calibrated and self._transform is not None:
                result["transform"] = self._transform.tolist()
            if self._recorded:
                result["recorded"] = list(self._recorded)
            return result

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Restore from persisted data."""
        with self._lock:
            transform = data.get("transform")
            if transform is not None:
                self._transform = np.array(transform, dtype=np.float64)
                self._calibrated = True
            recorded = data.get("recorded")
            if recorded:
                self._recorded = [tuple(r) for r in recorded]

    def save_to_prefs(self, prefs: Dict[str, Any]) -> None:
        """Save calibration data into the prefs dict."""
        prefs[PREFS_KEY] = self.to_dict()

    def load_from_prefs(self, prefs: Dict[str, Any]) -> None:
        """Load calibration data from the prefs dict."""
        data = prefs.get(PREFS_KEY)
        if isinstance(data, dict):
            self.load_from_dict(data)
