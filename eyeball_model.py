#!/usr/bin/env python3
"""
eyeball_model.py

Estimates the 3-D eyeball rotation centre from accumulated pupil observations
and computes accurate 3-D gaze vectors from that centre.

This module uses:
  1. A pinhole camera model: each detected pupil pixel maps to a unit ray in
     3-D camera space with a d = normalize([(u-px)/f, (v-py)/f, 1]).
  2. An eye-sphere model (radius R ≈ 12 mm).  The pupil is on the surface of
     a sphere of radius R centred at the eyeball rotation centre C.
  3. Ray–sphere intersection: given the camera ray d and the current estimate
     of C, we solve for the 3-D pupil position  P = t·d  exactly.
  4. A running EMA update: each new observation nudges C so that P sits on the
     sphere, converging to the true rotation center over ~30-100 frames.

Coordinate system
-----------------
  +X  right
  +Y  down  (standard image / OpenCV convention)
  +Z  into the scene (camera looks along +Z)

  The eye is in front of the camera (Z > 0).

Focal length note
-----------------
The tracker applies an 8× digital zoom before detection (crops centre 1/8 of
the frame then resizes back to original resolution).  If the physical webcam
has a horizontal FOV of ~60°, the effective FOV after 8× zoom is ~7.5°, giving

    f_eff ≈ (frame_w / 2) / tan(3.75°) ≈ frame_w * 7.65

Pass this value (or tune it) as `focal_length` when constructing EyeballModel.
A sensible default is supplied automatically from `zoom_factor`.
"""

import math
import numpy as np


class EyeballModel:
    """
    Running 3-D eyeball-centre estimator + gaze vector calculator.

    Parameters
    ----------
    frame_w, frame_h : int
        Frame dimensions in pixels (of the *processed* frame that reaches the
        detector, i.e. after any digital zoom has already been applied).
    focal_length : float or None
        Effective focal length in pixels.  If None, computed from
        `zoom_factor` and `base_fov_deg`.
    zoom_factor : float
        Digital zoom applied before this frame arrives (e.g. 8 for 8×).
        Used only when `focal_length` is None.
    base_fov_deg : float
        Horizontal FOV of the physical camera in degrees (before zoom).
        Used only when `focal_length` is None.
    eye_radius_mm : float
        Radius of the eye sphere from the rotation centre to the iris surface.
        Typical value: 12 mm.
    init_depth_mm : float
        Initial guess for the eye-to-camera distance in mm.
        Should be set to the expected physical viewing distance.
    smoothing_init : float
        EMA alpha used for the first `n_fast_frames` frames (faster warm-up).
    smoothing_steady : float
        EMA alpha used after `n_fast_frames` frames (stable tracking).
    n_fast_frames : int
        Number of frames to use the faster initial smoothing.
    """

    def __init__(
        self,
        frame_w: int,
        frame_h: int,
        focal_length: float = None,
        zoom_factor: float = 8.0,
        base_fov_deg: float = 60.0,
        eye_radius_mm: float = 12.0,
        init_depth_mm: float = 300.0,
        smoothing_init: float = 0.15,
        smoothing_steady: float = 0.03,
        n_fast_frames: int = 40,
    ):
        self.R = eye_radius_mm
        self.init_depth = init_depth_mm
        self.smoothing_init = smoothing_init
        self.smoothing_steady = smoothing_steady
        self.n_fast_frames = n_fast_frames

        # Principal point at image centre
        self.px = frame_w / 2.0
        self.py = frame_h / 2.0

        # Effective focal length (pixels)
        if focal_length is not None:
            self.f = float(focal_length)
        else:
            # f = (half_width) / tan(half_hfov_after_zoom)
            half_hfov_rad = math.radians(base_fov_deg / zoom_factor / 2.0)
            self.f = (frame_w / 2.0) / math.tan(half_hfov_rad)


        # Eyeball rotation centre in camera coords [mm].
        # Initialised at the image centre at the assumed depth.
        self.center = np.array([0.0, 0.0, float(init_depth_mm)])

        # Guard against updating the model twice on the same pupil position
        # (extract_gaze_numbers may be called more than once per frame).
        self._last_updated_center: tuple = None

        self.n_updates = 0


    def _pixel_to_ray(self, u: float, v: float) -> np.ndarray:
        """Return unit direction vector for image pixel (u, v)."""
        dx = (u - self.px) / self.f
        dy = (v - self.py) / self.f
        d = np.array([dx, dy, 1.0])
        return d / np.linalg.norm(d)

    def _ray_sphere_near(self, d: np.ndarray):
        """
        Nearest intersection of camera ray (origin 0, direction d) with the
        eye sphere (centre self.center, radius self.R).

        Returns (t, valid):
            t      depth along ray (P = t·d)
            valid  True if the ray actually hits the sphere
        """
        # t² – 2t(d·C) + |C|² – R² = 0
        dc = float(np.dot(d, self.center))
        disc = dc * dc - float(np.dot(self.center, self.center)) + self.R * self.R
        if disc < 0.0:
            return 0.0, False
        t = dc - math.sqrt(disc)
        return t, t > 0.0

    def update(self, pupil_center: tuple) -> None:
        """
        Ingest a pupil observation and refine the eyeball-centre estimate.

        Only processes each unique (x, y) once per call sequence to prevent
        double-updates when the same position is queried multiple times.

        Args:
            pupil_center : (x, y) pixel coordinates of detected pupil centre.
        """
        if pupil_center == self._last_updated_center:
            return
        self._last_updated_center = pupil_center

        u, v = pupil_center
        d = self._pixel_to_ray(u, v)
        t, valid = self._ray_sphere_near(d)
        if not valid:
            return

        # 3-D pupil position on the near side of the eye sphere
        P = t * d

        # Derive the centre update that places P exactly on the sphere:
        #   C_new = P + R · normalize(C_old – P)
        offset = self.center - P
        off_len = float(np.linalg.norm(offset))
        if off_len < 1e-9:
            return
        c_new = P + self.R * (offset / off_len)

        # Exponential moving average – faster during warm-up
        alpha = (
            self.smoothing_init
            if self.n_updates < self.n_fast_frames
            else self.smoothing_steady
        )
        self.center = (1.0 - alpha) * self.center + alpha * c_new
        self.n_updates += 1

    def get_gaze_data(self, pupil_center: tuple, ellipse_axes=None) -> dict:
        """
        Compute the 3-D gaze vector for the given pupil position.

        Uses the current eyeball-centre estimate + sphere intersection to find
        the exact 3-D pupil position, then returns gaze vectors and angles.

        Optionally uses the ellipse axes (from OrloskyPupil's RotatedRect) to
        verify / log the tilt angle independently; the sphere-intersection gaze
        direction is always used as the primary output.

        Args:
            pupil_center  : (x, y) pixel coordinates.
            ellipse_axes  : (axis1_px, axis2_px) full-diameter axes from
                            cv2.fitEllipse, i.e. ellipse[1].

        Returns dict with keys (same as old extract_gaze_numbers):
            'single_gaze_vector' : [x, y, z] unit vector in camera coords
            'single_angles'      : [theta_h_deg, theta_v_deg]
                                   theta_h > 0 → looking right
                                   theta_v > 0 → looking up
            'single_offset'      : [offset_x, offset_y]  (–1 to +1 range)
            'eye_center_3d'      : [x, y, z] current centre estimate in mm
            'tilt_deg'           : tilt angle from camera axis derived from
                                   ellipse axes (None if not provided)
        """
        u, v = pupil_center
        d = self._pixel_to_ray(u, v)
        t, valid = self._ray_sphere_near(d)

        if valid:
            P = t * d
        else:
            # Fallback: place pupil at assumed depth along the ray
            P = self.init_depth * d

        # Gaze vector: from eye centre outward through the pupil.
        # Sign convention check:
        #   Looking straight at camera → P ≈ C – R·ẑ → g = P–C ≈ (0,0,–R)
        #   → g_unit = (0, 0, –1) ✓
        gaze_raw = P - self.center
        g_len = float(np.linalg.norm(gaze_raw))
        if g_len < 1e-9:
            return None
        g = gaze_raw / g_len  # unit gaze vector

        # Horizontal and vertical angles
        # Camera looks along +Z, +X right, +Y down.
        # We negate g[2] so that looking at the camera gives a positive
        # denominator in atan2 (angles = 0 when looking straight ahead).
        theta_h = math.degrees(math.atan2(g[0], -g[2]))   # + = right
        theta_v = math.degrees(math.atan2(-g[1], -g[2]))  # + = up (flip Y)

        # Normalised 2-D offset (–1 … +1) for backward compatibility
        offset_x = float(g[0])
        offset_y = float(-g[1])  # flip Y so up = positive

        # Optional: tilt angle from ellipse axes (OrloskyPupil output)
        tilt_deg = None
        if ellipse_axes is not None:
            a1, a2 = float(ellipse_axes[0]), float(ellipse_axes[1])
            major = max(a1, a2)
            minor = min(a1, a2)
            if major > 1e-3:
                ratio = min(minor / major, 1.0)
                tilt_deg = math.degrees(math.acos(ratio))

        return {
            "single_gaze_vector": g.tolist(),
            "single_angles":      [theta_h, theta_v],
            "single_offset":      [offset_x, offset_y],
            "eye_center_3d":      self.center.tolist(),
            "tilt_deg":           tilt_deg,
        }


    def reset(self) -> None:
        """Reset the eyeball-centre estimate to the initial position."""
        self.center = np.array([0.0, 0.0, float(self.init_depth)])
        self._last_updated_center = None
        self.n_updates = 0

    def __repr__(self) -> str:
        return (
            f"EyeballModel(f={self.f:.0f}px, R={self.R}mm, "
            f"C=[{self.center[0]:.1f}, {self.center[1]:.1f}, {self.center[2]:.1f}]mm, "
            f"n={self.n_updates})"
        )
