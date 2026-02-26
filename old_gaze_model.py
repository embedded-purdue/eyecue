#!/usr/bin/env python3
"""
old_gaze_model.py

The original linear gaze mapping method used before the sphere-based
EyeballModel was introduced. Kept for comparison/benchmarking purposes.

This method computes gaze angles using:
  1. Pixel offset from ROI center: (pupil - roi_center) / roi_size
  2. Linear mapping to 3D: x_3d = offset * 12mm (eye radius)
  3. Z from circle equation: z = sqrt(R² - x² - y²)
  4. Angles: atan2(x, z), atan2(y, z)

Drawbacks:
  • No adaptive eye-center estimation — assumes fixed ROI center
  • Linear pixel→angle mapping breaks down at screen edges (~5-15° error)
  • Ignores perspective projection (pinhole camera model)

Advantages:
  • Simple, fast, zero warm-up
  • Works reasonably well near screen center
"""

import math
import numpy as np


class OldGazeModel:
    """
    Original linear gaze model from the main branch before EyeballModel.

    Matches the EyeballModel interface so ContourGazeTracker can swap between
    them without code changes.

    Parameters
    ----------
    frame_w, frame_h : int
        Frame dimensions (only used to compute ROI bounds; the rest is ignored).
    **kwargs
        Ignored (present for API compatibility with EyeballModel).
    """

    def __init__(self, frame_w: int, frame_h: int, **kwargs):
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.eye_radius_mm = 12.0

        # Fixed ROI center (the old code recomputed this every frame but it's constant)
        roi_width = int(frame_w * 0.6)
        roi_height = int(frame_h * 0.5)
        self.roi_center_x = int(frame_w * 0.2) + roi_width // 2
        self.roi_center_y = int(frame_h * 0.3) + roi_height // 2
        self.roi_width = roi_width
        self.roi_height = roi_height

        # Fake running state for status display compatibility
        self.n_updates = 0
        self.n_fast_frames = 1  # "converged" immediately

    def update(self, pupil_center: tuple) -> None:
        """
        Old model has no adaptive state — this is a no-op.
        Included for API compatibility with EyeballModel.
        """
        if pupil_center is not None:
            self.n_updates += 1

    def get_gaze_data(self, pupil_center: tuple, ellipse_axes=None) -> dict:
        """
        Compute gaze vector and angles using the original linear method.

        Returns the same dict keys as EyeballModel for drop-in compatibility.
        """
        if pupil_center is None:
            return None

        pupil_x, pupil_y = pupil_center

        # Pixel offset from fixed ROI center
        deviation_x = pupil_x - self.roi_center_x
        deviation_y = pupil_y - self.roi_center_y

        # Normalize by ROI dimensions
        offset_x = deviation_x / self.roi_width
        offset_y = -deviation_y / self.roi_height  # flip Y so up = positive

        # Map linearly to 3D on a sphere of radius 12mm
        x_3d = offset_x * self.eye_radius_mm
        y_3d = offset_y * self.eye_radius_mm
        z_3d = math.sqrt(max(0.0, self.eye_radius_mm**2 - x_3d**2 - y_3d**2))

        gaze_vector = np.array([x_3d, y_3d, z_3d])
        gaze_len = float(np.linalg.norm(gaze_vector))
        if gaze_len < 1e-9:
            return None
        gaze_vector = gaze_vector / gaze_len

        # Angles
        theta_h = math.degrees(math.atan2(gaze_vector[0], gaze_vector[2]))
        theta_v = math.degrees(math.atan2(gaze_vector[1], gaze_vector[2]))

        return {
            "single_gaze_vector": gaze_vector.tolist(),
            "single_angles":      [theta_h, theta_v],
            "single_offset":      [offset_x, offset_y],
            "eye_center_3d":      [0.0, 0.0, 0.0],   # no center estimation
            "tilt_deg":           None,
        }

    def reset(self) -> None:
        """Reset state (no-op for old model)."""
        self.n_updates = 0

    def __repr__(self) -> str:
        return f"OldGazeModel(ROI center=({self.roi_center_x}, {self.roi_center_y}))"
