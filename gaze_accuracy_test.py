#!/usr/bin/env python3
"""
gaze_accuracy_test.py

9-point gaze accuracy test.

Displays 9 targets (3x3 grid) on screen one at a time.  For each target the
user fixates while the tracker records predicted gaze positions, then the
average prediction is compared to the true target location.

Output
------
  • Terminal table: per-point target / predicted / error
  • On-screen results visualisation: target dots, predicted dots, error lines
  • Optional JSON report (press S on results screen)

Usage
-----
    python gaze_accuracy_test.py
    python gaze_accuracy_test.py --camera 1 --distance 500
    python gaze_accuracy_test.py --camera http://192.168.4.49 --distance 600
"""

import argparse
import json
import math
import time
from datetime import datetime

import cv2
import numpy as np
import pyautogui

from contour_gaze_tracker import ContourGazeTracker, ESP32CameraCapture
from pupil_detector import detect_pupil_contour
from test_gaze_angles import angles_to_screen_coords_cursorcontroller

# ---------------------------------------------------------------------------
# Target layout  – 3x3 grid with 15% margin on every edge
# ---------------------------------------------------------------------------
TARGETS_NORM = [
    (0.15, 0.15), (0.50, 0.15), (0.85, 0.15),   # top row
    (0.15, 0.50), (0.50, 0.50), (0.85, 0.50),   # middle row
    (0.15, 0.85), (0.50, 0.85), (0.85, 0.85),   # bottom row
]
TARGET_LABELS = [
    "Top-Left",    "Top-Center",  "Top-Right",
    "Mid-Left",    "Center",      "Mid-Right",
    "Bot-Left",    "Bot-Center",  "Bot-Right",
]

# ---------------------------------------------------------------------------
# Colours (BGR)
# ---------------------------------------------------------------------------
WHITE   = (255, 255, 255)
GRAY    = (160, 160, 160)
DGRAY   = (60,  60,  60)
CYAN    = (200, 200,  0)
GREEN   = (0,   255,  0)
RED     = (0,    60, 255)
YELLOW  = (0,   200, 200)
BLACK   = (0,     0,  0)


# ---------------------------------------------------------------------------
# Helper: draw a number of equally-spaced reference grid lines
# ---------------------------------------------------------------------------
def _draw_grid(canvas, color=DGRAY):
    h, w = canvas.shape[:2]
    for x in [int(w * f) for f in (0.15, 0.50, 0.85)]:
        cv2.line(canvas, (x, 0), (x, h), color, 1)
    for y in [int(h * f) for f in (0.15, 0.50, 0.85)]:
        cv2.line(canvas, (0, y), (w, y), color, 1)


# ---------------------------------------------------------------------------
# Main test class
# ---------------------------------------------------------------------------
class GazeAccuracyTest:
    """
    9-point gaze accuracy test.

    Parameters
    ----------
    camera_index       : int, video-file path, or ESP32 URL
    screen_distance_mm : physical eye-to-screen distance in mm
    warmup_secs        : how long to run the tracker before the test starts
                         (lets the EyeballModel converge)
    fixation_secs      : how long to show each dot before recording starts
    collection_secs    : how long to collect readings per target
    zoom_factor        : digital zoom applied to webcam frames (match tracker)
    """

    def __init__(
        self,
        camera_index=0,
        screen_distance_mm: float = 600.0,
        warmup_secs: float = 5.0,
        fixation_secs: float = 2.0,
        collection_secs: float = 2.5,
        zoom_factor: int = 8,
        gaze_model: str = 'sphere',
    ):
        self.camera_index      = camera_index
        self.screen_distance_mm = screen_distance_mm
        self.warmup_secs       = warmup_secs
        self.fixation_secs     = fixation_secs
        self.collection_secs   = collection_secs
        self.zoom_factor       = zoom_factor
        self.gaze_model        = gaze_model

        self.screen_w, self.screen_h = pyautogui.size()

        # Pixels per mm (~3.5 for a typical 24" 1080p monitor at 60 cm)
        self.screen_distance_px = screen_distance_mm * 3.5

        # Reuse ContourGazeTracker so it shares the same gaze model
        self.tracker = ContourGazeTracker(enable_metrics=False, gaze_model=gaze_model)

        # Pupil smoothing (matches contour_gaze_tracker settings)
        self.smoothed_pupil = None
        self.smooth_alpha   = 0.3
        self.frame_count    = 0
        self.is_local_camera = False

        # Per-point results
        self.results: list[dict] = []

    # ------------------------------------------------------------------ #
    # Camera helpers                                                       #
    # ------------------------------------------------------------------ #

    def _open_camera(self):
        is_esp32 = (
            isinstance(self.camera_index, str)
            and self.camera_index.startswith("http://")
        )
        if is_esp32:
            print(f"[info] Connecting to ESP32 camera: {self.camera_index}")
            return None, ESP32CameraCapture(self.camera_index)

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera/video: {self.camera_index}")

        self.is_local_camera = isinstance(self.camera_index, int)
        if self.is_local_camera:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            print("[info] Local webcam – applying 8x zoom")
        else:
            print(f"[info] Processing video file: {self.camera_index}")

        return cap, None

    def _read_frame(self, cap, esp32):
        if esp32:
            return esp32.read()
        return cap.read()

    def _cleanup(self, cap, esp32):
        if esp32:
            esp32.release()
        elif cap:
            cap.release()
        cv2.destroyAllWindows()

    # ------------------------------------------------------------------ #
    # Frame processing                                                     #
    # ------------------------------------------------------------------ #

    def _process_frame(self, frame):
        """
        Apply zoom → detect pupil → smooth → extract gaze → map to screen.

        Returns (frame, stable_pupil, gaze_data, screen_pos).
        screen_pos is None when no pupil is detected.
        """
        # Mirror-correct the webcam frame so left/right match the user's perspective.
        # test_gaze_angles.py does this before anything else; we must match it exactly.
        if self.is_local_camera and frame is not None:
            frame = cv2.flip(frame, 1)

        # 8× centre crop for local webcam
        if self.is_local_camera and frame is not None:
            h, w = frame.shape[:2]
            cw = w // self.zoom_factor
            ch = h // self.zoom_factor
            cx = (w - cw) // 2
            cy = (h - ch) // 2
            frame = frame[cy : cy + ch, cx : cx + cw]
            frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)

        self.frame_count += 1

        pupil_center, _ = detect_pupil_contour(frame)

        # Exponential smoothing
        if pupil_center is not None:
            if self.smoothed_pupil is None:
                self.smoothed_pupil = pupil_center
            else:
                self.smoothed_pupil = (
                    int(self.smooth_alpha * pupil_center[0]
                        + (1 - self.smooth_alpha) * self.smoothed_pupil[0]),
                    int(self.smooth_alpha * pupil_center[1]
                        + (1 - self.smooth_alpha) * self.smoothed_pupil[1]),
                )
        elif self.frame_count % 10 == 0:
            self.smoothed_pupil = None

        stable = self.smoothed_pupil
        gaze_data = None
        screen_pos = None

        if stable is not None:
            gaze_data = self.tracker.extract_gaze_numbers(stable, frame.shape)
            if gaze_data:
                angle_h, angle_v = gaze_data["single_angles"]
                screen_pos = angles_to_screen_coords_cursorcontroller(
                    angle_h, angle_v,
                    self.screen_w, self.screen_h,
                    screen_distance_pixels=self.screen_distance_px,
                )

        return frame, stable, gaze_data, screen_pos

    # ------------------------------------------------------------------ #
    # Drawing helpers                                                      #
    # ------------------------------------------------------------------ #

    def _blank(self):
        """Return a fresh dark canvas the size of the test window."""
        canvas = np.full((self.screen_h, self.screen_w, 3), 18, dtype=np.uint8)
        _draw_grid(canvas)
        return canvas

    def _draw_target(self, canvas, pos, phase, progress, idx, total):
        """
        Draw the active target with phase-specific visual feedback.

        phase    : 'ready' | 'fixate' | 'collect'
        progress : 0.0 → 1.0 completion fraction for the current phase
        """
        x, y = pos

        # Phase-specific arc (progress ring)
        if phase == "fixate":
            ring_col = YELLOW
        elif phase == "collect":
            ring_col = GREEN
        else:
            ring_col = DGRAY

        if phase in ("fixate", "collect"):
            angle_end = int(360 * progress)
            cv2.ellipse(canvas, (x, y), (46, 46), -90,
                        0, angle_end, ring_col, 4)

        # Background reference circle
        cv2.circle(canvas, (x, y), 42, DGRAY, 1)

        # Crosshair
        cv2.line(canvas, (x - 22, y), (x + 22, y), WHITE, 2)
        cv2.line(canvas, (x, y - 22), (x, y + 22), WHITE, 2)
        cv2.circle(canvas, (x, y), 6, WHITE, -1)

        # Phase label – above the ring for bottom-row targets, below for others.
        # This keeps the label clear of the bottom-of-screen status bar.
        if phase == "ready":
            label, lc = "LOOK HERE", YELLOW
        elif phase == "fixate":
            label, lc = "HOLD...", CYAN
        else:
            label, lc = "RECORDING", GREEN

        if y > self.screen_h * 0.7:
            label_y = y - 62   # above the ring (bottom row)
        else:
            label_y = y + 72   # below the ring (top / middle rows)

        cv2.putText(canvas, label,
                    (x - 52, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, lc, 2)

        # Point counter (top-left)
        cv2.putText(canvas, f"Point {idx + 1} / {total}",
                    (24, 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, GRAY, 2)

    def _draw_status_panel(self, canvas, stable, gaze_data):
        """
        Full-width single-row bar at the very bottom of the canvas.

        Layout (left → right):
          ● DET/NO  |  MODEL: LOCKED (47) [====]  |  DEPTH 312 mm  |  GAZE H:+5° V:-2°  |  Q=abort
        """
        em     = self.tracker.eyeball_model
        n_up   = em.n_updates    if em else 0
        n_fast = em.n_fast_frames if em else 40
        locked = n_up >= n_fast

        bar_h  = 42
        by0    = self.screen_h - bar_h
        mid_y  = by0 + 28   # text baseline inside bar

        # Background strip
        cv2.rectangle(canvas, (0, by0), (self.screen_w, self.screen_h),
                      (18, 18, 18), -1)
        cv2.line(canvas, (0, by0), (self.screen_w, by0), DGRAY, 1)

        x = 14

        # ── Pupil detection ──────────────────────────────────────────────
        det_col = GREEN if stable is not None else RED
        det_txt = "DETECTED" if stable is not None else "NO SIGNAL"
        cv2.circle(canvas, (x + 7, mid_y - 7), 7, det_col, -1)
        x += 18
        cv2.putText(canvas, det_txt, (x, mid_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, det_col, 1)
        x += int(cv2.getTextSize(det_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)[0][0]) + 18

        cv2.line(canvas, (x, by0 + 8), (x, self.screen_h - 6), DGRAY, 1)
        x += 12

        # ── Model convergence ─────────────────────────────────────────────
        if locked:
            bar_col = GREEN
            mdl_txt = f"MODEL LOCKED ({n_up})"
            fill_f  = 1.0
        else:
            bar_col = YELLOW
            mdl_txt = f"MODEL {n_up}/{n_fast}"
            fill_f  = n_up / max(n_fast, 1)

        cv2.putText(canvas, mdl_txt, (x, mid_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, bar_col, 1)
        x += int(cv2.getTextSize(mdl_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)[0][0]) + 8
        # Mini progress bar (80px wide)
        bx0, bx1 = x, x + 80
        bby0, bby1 = mid_y - 12, mid_y - 4
        cv2.rectangle(canvas, (bx0, bby0), (bx1, bby1), DGRAY, -1)
        cv2.rectangle(canvas, (bx0, bby0), (bx0 + int(80 * fill_f), bby1), bar_col, -1)
        x = bx1 + 18

        cv2.line(canvas, (x, by0 + 8), (x, self.screen_h - 6), DGRAY, 1)
        x += 12

        # ── Eye depth ────────────────────────────────────────────────────
        if em and gaze_data:
            depth_txt = f"DEPTH {gaze_data['eye_center_3d'][2]:.0f} mm"
            depth_col = GRAY
        else:
            depth_txt, depth_col = "DEPTH --", DGRAY
        cv2.putText(canvas, depth_txt, (x, mid_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, depth_col, 1)
        x += int(cv2.getTextSize(depth_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)[0][0]) + 18

        cv2.line(canvas, (x, by0 + 8), (x, self.screen_h - 6), DGRAY, 1)
        x += 12

        # ── Gaze angles ───────────────────────────────────────────────────
        if gaze_data:
            h_deg, v_deg = gaze_data["single_angles"]
            ang_txt = f"GAZE  H={h_deg:+.1f}\u00b0  V={v_deg:+.1f}\u00b0"
            ang_col = CYAN
        else:
            ang_txt, ang_col = "GAZE  H=--  V=--", DGRAY
        cv2.putText(canvas, ang_txt, (x, mid_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, ang_col, 1)

        # ── Abort hint (far right) ────────────────────────────────────────
        hint = "Q = abort"
        hw = int(cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0])
        cv2.putText(canvas, hint, (self.screen_w - hw - 14, mid_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, DGRAY, 1)

    def _draw_live_cursor(self, canvas, screen_pos):
        """
        Draw a translucent ring at the current predicted gaze position so
        the user can see in real time where the model thinks they're looking.
        """
        if screen_pos is None:
            return
        gx, gy = int(screen_pos[0]), int(screen_pos[1])
        # Clamp to canvas bounds
        gx = max(20, min(self.screen_w  - 20, gx))
        gy = max(20, min(self.screen_h - 20, gy))
        # Outer ring
        cv2.circle(canvas, (gx, gy), 24, CYAN, 2)
        # Inner dot
        cv2.circle(canvas, (gx, gy), 5, CYAN, -1)
        # Small cross-hair
        cv2.line(canvas, (gx - 14, gy), (gx + 14, gy), CYAN, 1)
        cv2.line(canvas, (gx, gy - 14), (gx, gy + 14), CYAN, 1)

    def _draw_camera_thumb(self, canvas, frame, stable):
        """Draw camera thumbnail in top-right with detection dot."""
        if frame is None:
            return
        th_h, th_w = 120, 160
        thumb = cv2.resize(frame, (th_w, th_h))
        x0 = self.screen_w - th_w - 12
        y0 = 12
        canvas[y0 : y0 + th_h, x0 : x0 + th_w] = thumb
        # Detection dot
        dot_col = GREEN if stable is not None else RED
        cv2.circle(canvas, (x0 + th_w - 8, y0 + 8), 6, dot_col, -1)

    def _draw_intro(self, canvas, warmup_remaining, frame=None, stable=None,
                    gaze_data=None, screen_pos=None):
        cx = self.screen_w  // 2
        cy = self.screen_h // 2

        cv2.putText(canvas, "9-Point Gaze Accuracy Test",
                    (cx - 310, cy - 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, WHITE, 2)

        if warmup_remaining > 0:
            cv2.putText(canvas,
                        f"Warming up...  look around  ({warmup_remaining:.1f} s)",
                        (cx - 290, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, CYAN, 2)
            cv2.putText(canvas,
                        "Move your eyes to all corners so the model can initialise",
                        (cx - 320, cy + 46),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, GRAY, 1)
        else:
            cv2.putText(canvas, "Ready!  Press SPACE to begin",
                        (cx - 210, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, GREEN, 2)
            cv2.putText(canvas,
                        "Each of the 9 dots will appear one at a time.",
                        (cx - 270, cy + 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, GRAY, 1)
            cv2.putText(canvas,
                        "Hold your gaze on each dot when it turns GREEN.",
                        (cx - 270, cy + 72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, GRAY, 1)

        # Status panel + live cursor + thumbnail on the intro screen too
        self._draw_status_panel(canvas, stable, gaze_data)
        self._draw_live_cursor(canvas, screen_pos)
        self._draw_camera_thumb(canvas, frame, stable)

    def _draw_results_screen(self, canvas):
        """Visualise all targets and predictions with error lines."""

        m = self._compute_metrics()

        # ── Top header (fits above the first target row at 0.15*h) ───────
        # Title
        model_label = "OLD MODEL" if self.gaze_model == "old" else "SPHERE MODEL"
        cv2.putText(canvas, f"Gaze Accuracy Results  [{model_label}]",
                    (self.screen_w // 2 - 310, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, WHITE, 2)

        # Accuracy % – keep entirely above y = 0.15*screen_h - 20 (ring top)
        acc = m.get("accuracy_pct")
        if acc is not None:
            if acc >= 90:
                acc_col = GREEN
            elif acc >= 75:
                acc_col = YELLOW
            else:
                acc_col = RED
            acc_str = f"{acc:.1f}%"
            # label at y=62, number baseline at y=110  (scale 1.5 ≈ 42px tall → top ≈ y=68)
            # first target circle top = 0.15*h - 18 ≈ y=126 on 720p, y=144 on 1080p
            cv2.putText(canvas, "OVERALL ACCURACY",
                        (self.screen_w // 2 - 120, 62),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.60, GRAY, 1)
            tw = int(cv2.getTextSize(acc_str, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)[0][0])
            cv2.putText(canvas, acc_str,
                        (self.screen_w // 2 - tw // 2, 112),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, acc_col, 3)

        # Compute max error for colour scaling
        errs = [r["error_px"] for r in self.results if r["error_px"] is not None]
        max_err = max(errs) if errs else 1.0

        for r in self.results:
            tx, ty = r["target_px"]

            # Target marker: white cross inside circle
            cv2.circle(canvas, (tx, ty), 18, WHITE, 2)
            cv2.line(canvas, (tx - 12, ty), (tx + 12, ty), WHITE, 2)
            cv2.line(canvas, (tx, ty - 12), (tx, ty + 12), WHITE, 2)

            if r["predicted_px"] is None:
                cv2.putText(canvas, "NO DATA",
                            (tx - 36, ty + 36),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, RED, 1)
                continue

            px, py = r["predicted_px"]
            err   = r["error_px"]

            # Colour: green (close) → red (far)
            ratio = min(err / max_err, 1.0)
            col   = (int(ratio * 30), int((1 - ratio) * 220), int(ratio * 255))

            # Error line from target to prediction
            cv2.arrowedLine(canvas, (tx, ty), (px, py), col, 2, tipLength=0.2)

            # Prediction dot
            cv2.circle(canvas, (px, py), 9, col, -1)
            cv2.circle(canvas, (px, py), 9, WHITE, 1)

            # Error label at midpoint
            mid = ((tx + px) // 2 + 6, (ty + py) // 2 - 6)
            cv2.putText(canvas, f"{err:.0f}px",
                        mid, cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1)

        # ── Bottom strip: summary stats + legend + hints ─────────────────
        # Sits below the bottom target row (0.85*h) — same strip as status bar
        strip_h = 58
        sy0 = self.screen_h - strip_h
        cv2.rectangle(canvas, (0, sy0), (self.screen_w, self.screen_h),
                      (18, 18, 18), -1)
        cv2.line(canvas, (0, sy0), (self.screen_w, sy0), DGRAY, 1)

        raw = m.get("raw", {})
        mean_px  = raw.get("mean_px")
        screen_diag = math.sqrt(self.screen_w**2 + self.screen_h**2)

        # Row 1: key numbers
        row1 = []
        if mean_px is not None:
            row1.append(f"Mean error: {mean_px:.0f} px ({mean_px/screen_diag*100:.1f}% of screen)")
        row1.append(f"Median: {raw.get('median_px', 0):.0f} px")
        row1.append(f"Best: {raw.get('min_px', 0):.0f} px")
        row1.append(f"Worst: {raw.get('max_px', 0):.0f} px")
        row1.append(f"Points: {raw.get('n_valid', 0)}/{raw.get('n_total', 0)}")
        row1_txt = "    |    ".join(row1)
        cv2.putText(canvas, row1_txt, (14, sy0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, GRAY, 1)

        # Row 2: legend + hints
        lx = 14
        ly2 = sy0 + 46
        cv2.circle(canvas, (lx + 10, ly2 - 6), 9, WHITE, 2)
        cv2.line(canvas, (lx, ly2 - 6), (lx + 20, ly2 - 6), WHITE, 2)
        cv2.putText(canvas, "= Target", (lx + 26, ly2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.43, GRAY, 1)
        lx += 120
        cv2.circle(canvas, (lx + 8, ly2 - 6), 7, GREEN, -1)
        cv2.putText(canvas, "= Predicted gaze", (lx + 22, ly2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.43, GRAY, 1)

        hint = "S = save JSON    Q = quit"
        hw = int(cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.46, 1)[0][0])
        cv2.putText(canvas, hint, (self.screen_w - hw - 14, ly2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, DGRAY, 1)

    # ------------------------------------------------------------------ #
    # Metrics                                                              #
    # ------------------------------------------------------------------ #

    def _compute_metrics(self) -> dict:
        valid = [r for r in self.results if r["error_px"] is not None]
        if not valid:
            return {"lines": ["No valid data collected"], "raw": {}, "accuracy_pct": None}

        errs        = np.array([r["error_px"] for r in valid])
        mean_err    = float(np.mean(errs))
        median_err  = float(np.median(errs))
        std_err     = float(np.std(errs))
        max_err     = float(np.max(errs))
        min_err     = float(np.min(errs))
        screen_diag = math.sqrt(self.screen_w ** 2 + self.screen_h ** 2)

        # Overall accuracy: complement of mean error relative to screen diagonal.
        # 100% = perfect; 0% = mean error equals the full screen diagonal.
        # Each point's prediction is the average of all readings collected during
        # the "RECORDING" phase, compared to the exact crosshair position.
        accuracy_pct = max(0.0, 100.0 * (1.0 - mean_err / screen_diag))

        lines = [
            f"ACCURACY:         {accuracy_pct:.1f}%",
            f"Points collected: {len(valid)} / {len(self.results)}",
            f"Mean error:       {mean_err:.1f} px  ({mean_err / screen_diag * 100:.1f}% of screen)",
            f"Median error:     {median_err:.1f} px",
            f"Std deviation:    {std_err:.1f} px",
            f"Best point:       {min_err:.1f} px",
            f"Worst point:      {max_err:.1f} px",
        ]

        return {
            "lines":        lines,
            "accuracy_pct": accuracy_pct,
            "raw": {
                "accuracy_pct": accuracy_pct,
                "mean_px":      mean_err,
                "median_px":    median_err,
                "std_px":       std_err,
                "min_px":       min_err,
                "max_px":       max_err,
                "n_valid":      len(valid),
                "n_total":      len(self.results),
            },
        }

    def print_report(self):
        """Print a formatted accuracy table to the terminal."""
        model_label = "OLD MODEL" if self.gaze_model == "old" else "SPHERE MODEL"
        print("\n" + "=" * 68)
        print(f"  9-POINT GAZE ACCURACY TEST RESULTS  [{model_label}]")
        print("=" * 68)
        print(f"  {'Point':<14}  {'Target':>12}  {'Predicted':>12}  {'Error':>9}  {'Samples':>7}")
        print("  " + "-" * 64)

        for i, r in enumerate(self.results):
            name     = TARGET_LABELS[i]
            tx, ty   = r["target_px"]
            n        = r["n_readings"]
            if r["predicted_px"] is not None:
                px, py = r["predicted_px"]
                err    = r["error_px"]
                print(f"  {name:<14}  ({tx:4d},{ty:4d})  ({px:4d},{py:4d})  {err:7.1f}px  {n:7d}")
            else:
                print(f"  {name:<14}  ({tx:4d},{ty:4d})  {'NO DATA':>12}  {'---':>9}  {n:7d}")

        print("  " + "-" * 64)
        m = self._compute_metrics()
        acc = m.get("accuracy_pct")
        if acc is not None:
            print(f"\n  >>> OVERALL ACCURACY: {acc:.1f}% <<<\n")
        for line in m["lines"][1:]:   # skip the ACCURACY line – already printed above
            print(f"  {line}")
        print("=" * 68 + "\n")

    def save_report(self, filename: str = None) -> str:
        if filename is None:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_suffix = "old" if self.gaze_model == "old" else "sphere"
            filename = f"gaze_accuracy_{model_suffix}_{ts}.json"

        data = {
            "timestamp":          datetime.now().isoformat(),
            "gaze_model":         self.gaze_model,
            "screen_size_px":     [self.screen_w, self.screen_h],
            "screen_distance_mm": self.screen_distance_mm,
            "metrics":            self._compute_metrics()["raw"],
            "per_point":          self.results,
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2, default=str)

        print(f"[info] Saved to: {filename}")
        return filename

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    def run(self):
        cap, esp32 = self._open_camera()

        win = "Gaze Accuracy Test"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, self.screen_w, self.screen_h)
        cv2.moveWindow(win, 0, 0)

        # ── Phase 0: warm-up ──────────────────────────────────────────────
        print(f"[info] Warm-up ({self.warmup_secs:.0f}s) – look around so the model can converge")
        warmup_end   = time.time() + self.warmup_secs
        ready_to_go  = False

        warmup_frame  = None
        warmup_stable = None
        warmup_gaze   = None
        warmup_pos    = None

        while True:
            ret, frame = self._read_frame(cap, esp32)
            if not ret or frame is None:
                continue

            warmup_frame, warmup_stable, warmup_gaze, warmup_pos = \
                self._process_frame(frame)

            remaining = warmup_end - time.time()
            if remaining <= 0:
                ready_to_go = True

            canvas = self._blank()
            self._draw_intro(
                canvas,
                max(remaining, 0) if not ready_to_go else 0,
                frame=warmup_frame,
                stable=warmup_stable,
                gaze_data=warmup_gaze,
                screen_pos=warmup_pos,
            )
            cv2.imshow(win, canvas)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                self._cleanup(cap, esp32)
                return
            if key == ord(" ") and ready_to_go:
                break

        # ── Phase 1: 9-point test ─────────────────────────────────────────
        targets_px = [
            (int(nx * self.screen_w), int(ny * self.screen_h))
            for nx, ny in TARGETS_NORM
        ]

        aborted = False
        for idx, target_px in enumerate(targets_px):
            tx, ty = target_px
            print(f"[info] Point {idx + 1}/9: {TARGET_LABELS[idx]}  target=({tx}, {ty})")

            readings: list[tuple] = []

            # Sub-phases: ready → fixate → collect
            for phase, duration in [
                ("ready",   1.0),
                ("fixate",  self.fixation_secs),
                ("collect", self.collection_secs),
            ]:
                phase_start = time.time()
                while True:
                    elapsed  = time.time() - phase_start
                    if elapsed >= duration:
                        break
                    progress = elapsed / duration

                    ret, frame = self._read_frame(cap, esp32)
                    if not ret or frame is None:
                        continue

                    frame, stable, gaze_data, screen_pos = self._process_frame(frame)

                    # Collect predicted screen positions during the recording phase
                    if phase == "collect" and screen_pos is not None:
                        readings.append(screen_pos)

                    canvas = self._blank()
                    self._draw_target(canvas, target_px, phase, progress,
                                      idx, len(targets_px))
                    self._draw_live_cursor(canvas, screen_pos)
                    self._draw_status_panel(canvas, stable, gaze_data)
                    self._draw_camera_thumb(canvas, frame, stable)

                    cv2.imshow(win, canvas)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        aborted = True
                        break

                if aborted:
                    break

            if aborted:
                print("[info] Test aborted by user")
                break

            # Store result for this target
            if readings:
                pred_x = int(np.mean([r[0] for r in readings]))
                pred_y = int(np.mean([r[1] for r in readings]))
                error  = math.sqrt((pred_x - tx) ** 2 + (pred_y - ty) ** 2)
                self.results.append({
                    "name":         TARGET_LABELS[idx],
                    "target_px":    [tx, ty],
                    "predicted_px": [pred_x, pred_y],
                    "error_px":     error,
                    "n_readings":   len(readings),
                })
                print(f"        predicted=({pred_x}, {pred_y})  "
                      f"error={error:.1f}px  ({len(readings)} samples)")
            else:
                self.results.append({
                    "name":         TARGET_LABELS[idx],
                    "target_px":    [tx, ty],
                    "predicted_px": None,
                    "error_px":     None,
                    "n_readings":   0,
                })
                print("        no gaze readings collected for this point")

        # ── Phase 2: results ──────────────────────────────────────────────
        self.print_report()
        print("[info] Results screen: press S to save JSON, Q to quit")

        while True:
            canvas = self._blank()
            self._draw_results_screen(canvas)
            cv2.imshow(win, canvas)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s"):
                self.save_report()

        self._cleanup(cap, esp32)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="9-point gaze accuracy test")
    parser.add_argument(
        "--camera", type=str, default="0",
        help="Camera index (int), video path, or ESP32 URL",
    )
    parser.add_argument(
        "--distance", type=float, default=600.0,
        help="Eye-to-screen distance in mm (default: 600)",
    )
    parser.add_argument(
        "--warmup", type=float, default=5.0,
        help="Warm-up duration in seconds before the test starts (default: 5)",
    )
    parser.add_argument(
        "--fixation", type=float, default=2.0,
        help="Seconds to hold gaze before recording starts per point (default: 2)",
    )
    parser.add_argument(
        "--collect", type=float, default=2.5,
        help="Seconds to collect readings per point (default: 2.5)",
    )
    parser.add_argument(
        "--model", type=str, default="sphere", choices=["sphere", "old"],
        help="Gaze model: 'sphere' (new adaptive) or 'old' (linear ROI) (default: sphere)",
    )
    args = parser.parse_args()

    try:
        camera_input = int(args.camera)
    except ValueError:
        camera_input = args.camera

    test = GazeAccuracyTest(
        camera_index=camera_input,
        screen_distance_mm=args.distance,
        warmup_secs=args.warmup,
        fixation_secs=args.fixation,
        collection_secs=args.collect,
        gaze_model=args.model,
    )
    test.run()


if __name__ == "__main__":
    main()
