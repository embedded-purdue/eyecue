"""
Calibration service.

Fits a 2nd-order polynomial mapping from *normalized pupil pixel coordinates*
to screen pixel coordinates, using a 9-point (3x3 grid) calibration:

    sx = a0 + a1·nx + a2·ny + a3·nx² + a4·ny² + a5·nx·ny
    sy = b0 + b1·nx + b2·ny + b3·nx² + b4·ny² + b5·nx·ny

Why this design:
    * Input is raw pupil pixel position normalised to [0, 1] across the camera
      frame. We do NOT use the synthetic "gaze angles" computed from a
      fictional 12 mm eye radius — the polynomial learns the full distortion
      directly from data, including any off-axis camera placement.
    * 2nd-order has 6 terms per axis; 9 points gives 3 degrees of overdetermination
      so the least-squares fit is well-behaved without overfitting.
    * Quick-recalibrate shifts only the constant term to compensate for drift
      without losing the learned distortion.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# 9-point calibration layout (3x3 grid, fractions of screen).
# Avoid the absolute screen edges so the dot is fully visible.
CALIBRATION_POINTS = [
    (0.08, 0.08), (0.50, 0.08), (0.92, 0.08),
    (0.08, 0.50), (0.50, 0.50), (0.92, 0.50),
    (0.08, 0.92), (0.50, 0.92), (0.92, 0.92),
]

PREFS_KEY = "calibration_data"
SCHEMA_VERSION = 2  # bumped — incompatible with old affine-on-angles prefs


def _features(nx: float, ny: float) -> np.ndarray:
    """Polynomial feature vector: [1, nx, ny, nx², ny², nx·ny]."""
    return np.array([1.0, nx, ny, nx * nx, ny * ny, nx * ny], dtype=np.float64)


class CalibrationState:
    """Owns the active calibration session and the fitted polynomial coefficients."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active = False
        self._point_index = 0
        # recorded pairs: list of (nx, ny, screen_x, screen_y)
        self._recorded: List[Tuple[float, float, float, float]] = []
        # coefficient matrix shape (2, 6): row 0 -> x, row 1 -> y
        self._coeffs: Optional[np.ndarray] = None
        self._calibrated = False

    # ── status helpers ─────────────────────────────────────────────────

    @property
    def is_calibrated(self) -> bool:
        with self._lock:
            return self._calibrated

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    # ── session lifecycle ──────────────────────────────────────────────

    def start(self) -> Dict[str, Any]:
        with self._lock:
            self._active = True
            self._point_index = 0
            self._recorded = []
            return self._snapshot()

    def cancel(self) -> Dict[str, Any]:
        with self._lock:
            self._active = False
            self._point_index = 0
            self._recorded = []
            return self._snapshot()

    def record_point(
        self,
        point_index: int,
        nx: float,
        ny: float,
        screen_x: float,
        screen_y: float,
    ) -> Dict[str, Any]:
        """Record a normalized pupil position at a known screen target."""
        with self._lock:
            if not self._active:
                raise ValueError("Calibration not active")
            if point_index != self._point_index:
                raise ValueError(
                    f"Expected point {self._point_index}, got {point_index}"
                )
            self._recorded.append((
                float(nx), float(ny),
                float(screen_x), float(screen_y),
            ))
            self._point_index += 1
            return self._snapshot()

    def finish(self) -> Dict[str, Any]:
        with self._lock:
            if len(self._recorded) < 6:
                raise ValueError(
                    f"Need at least 6 points for polynomial fit, have {len(self._recorded)}"
                )
            self._fit()
            self._active = False
            return self._snapshot()

    def quick_recalibrate(
        self,
        nx: float,
        ny: float,
        screen_x: float,
        screen_y: float,
    ) -> Dict[str, Any]:
        """
        Shift the constant terms so the current pupil position maps exactly
        to (screen_x, screen_y). Preserves the learned distortion.
        """
        with self._lock:
            if not self._calibrated or self._coeffs is None:
                raise ValueError("No existing calibration to adjust")

            current_x, current_y = self._apply(nx, ny)
            self._coeffs[0, 0] += float(screen_x) - current_x
            self._coeffs[1, 0] += float(screen_y) - current_y
            return self._snapshot()

    # ── apply ──────────────────────────────────────────────────────────

    def apply(self, nx: float, ny: float) -> Optional[Tuple[int, int]]:
        """Map normalized pupil position to screen pixel coordinates."""
        with self._lock:
            if not self._calibrated or self._coeffs is None:
                return None
            x, y = self._apply(nx, ny)
            return int(round(x)), int(round(y))

    def _apply(self, nx: float, ny: float) -> Tuple[float, float]:
        feats = _features(nx, ny)
        x = float(self._coeffs[0] @ feats)
        y = float(self._coeffs[1] @ feats)
        return x, y

    # ── fitting ────────────────────────────────────────────────────────

    def _fit(self) -> None:
        n = len(self._recorded)
        A = np.zeros((n, 6), dtype=np.float64)
        Bx = np.zeros(n, dtype=np.float64)
        By = np.zeros(n, dtype=np.float64)
        for i, (nx, ny, sx, sy) in enumerate(self._recorded):
            A[i] = _features(nx, ny)
            Bx[i] = sx
            By[i] = sy

        # ridge term keeps the fit numerically stable even if a couple of
        # the 9 captured points happen to be near-collinear in pupil space
        ridge = 1e-3 * np.eye(6)
        AtA = A.T @ A + ridge
        params_x = np.linalg.solve(AtA, A.T @ Bx)
        params_y = np.linalg.solve(AtA, A.T @ By)

        self._coeffs = np.vstack([params_x, params_y])
        self._calibrated = True

    # ── snapshot / persistence ─────────────────────────────────────────

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "active": self._active,
            "calibrated": self._calibrated,
            "point_index": self._point_index,
            "total_points": len(CALIBRATION_POINTS),
            "recorded_count": len(self._recorded),
        }

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            result = self._snapshot()
            result["schema_version"] = SCHEMA_VERSION
            if self._calibrated and self._coeffs is not None:
                result["coeffs"] = self._coeffs.tolist()
            if self._recorded:
                result["recorded"] = list(self._recorded)
            return result

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        with self._lock:
            # discard incompatible legacy data (affine-on-angles)
            if int(data.get("schema_version", 0)) != SCHEMA_VERSION:
                return
            coeffs = data.get("coeffs")
            if coeffs is not None:
                arr = np.array(coeffs, dtype=np.float64)
                if arr.shape == (2, 6):
                    self._coeffs = arr
                    self._calibrated = True
            recorded = data.get("recorded")
            if recorded:
                try:
                    self._recorded = [tuple(r) for r in recorded]
                except Exception:
                    self._recorded = []

    def save_to_prefs(self, prefs: Dict[str, Any]) -> None:
        prefs[PREFS_KEY] = self.to_dict()

    def load_from_prefs(self, prefs: Dict[str, Any]) -> None:
        data = prefs.get(PREFS_KEY)
        if isinstance(data, dict):
            self.load_from_dict(data)
