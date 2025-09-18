#!/usr/bin/env python3
"""
eyecue.py

Advanced gaze tracker with dual calibration:
  - 9-point grid calibration (anchor points)
  - Automatic moving-cursor calibration (dense coverage) — runs immediately after grid
  - MediaPipe Face Mesh (iris + eye landmarks)
  - Geometric baseline + ExtraTrees + KNN residuals + Ridge fallback
  - Queue/deque-based safe sample collection
  - Preview overlay with detected iris center (green) during calibration so user can see tracking
  - Robust outlier rejection (median+MAD)
  - Handles missing camera frames gracefully and will not crash on empty calibration sets
  - Toggle mirror, toggle mouse, recalibrate, quit

Usage:
    python3 eyecue.py
"""

import os
import time
import argparse
import atexit
import math
import cv2
import mediapipe as mp
import numpy as np
import pyautogui
import tkinter as tk
from collections import deque
from scipy.spatial.distance import euclidean
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error
import traceback

# -------------------------
# Config / Tunables
# -------------------------
FRAME_W = 640
FRAME_H = 480
FPS_TARGET = 30

SAMPLES_PER_POINT = 30        # increase for more stable calibration per point
MAX_CAL_POINT_TIME = 5.0     # seconds per grid point maximum
OUTLIER_MAD_THRESH = 2.5

EXTRA_TREES_ESTIMATORS = 200
EXTRA_TREES_DEPTH = 18

KNN_NEIGHBORS = 4

EXP_SMOOTH = 0.28            # runtime exponential smoothing
MIN_CAL_POINTS = 9

# Moving cursor calibration parameters
MOVING_CAL_DURATION = 18.0    # seconds (total)
MOVING_CAL_SAMPLING_RATE = 25  # target effective rate
MOVING_CAL_MIN_SAMPLES = 180   # min samples to accept from moving cursor stage
MOVING_PATH_TYPE = "zigzag"    # "line", "zigzag", "spiral"

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# -------------------------
# Utility / Core class
# -------------------------
class EyecueAdvancedDualCalib:
    def __init__(self, mirror=True):
        self.mirror = bool(mirror)
        self.screen_w, self.screen_h = pyautogui.size()

        # mediapipe setup
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.65, min_tracking_confidence=0.70
        )

        # MediaPipe landmark indices
        self.LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
        self.RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]
        self.LEFT_IRIS = [474, 475, 476, 477]
        self.RIGHT_IRIS = [469, 470, 471, 472]
        self.LEFT_CENTER = 468
        self.RIGHT_CENTER = 473

        # models
        self.scaler = StandardScaler()
        self.global_x = ExtraTreesRegressor(n_estimators=EXTRA_TREES_ESTIMATORS,
                                            max_depth=EXTRA_TREES_DEPTH, n_jobs=-1, random_state=42)
        self.global_y = ExtraTreesRegressor(n_estimators=EXTRA_TREES_ESTIMATORS,
                                            max_depth=EXTRA_TREES_DEPTH, n_jobs=-1, random_state=43)
        self.ridge_x = Ridge(alpha=1.0)
        self.ridge_y = Ridge(alpha=1.0)
        self.knn_res_x = KNeighborsRegressor(n_neighbors=KNN_NEIGHBORS)
        self.knn_res_y = KNeighborsRegressor(n_neighbors=KNN_NEIGHBORS)

        self.is_calibrated = False

        # runtime smoothing / state
        self.last_x = self.screen_w / 2.0
        self.last_y = self.screen_h / 2.0
        self.running = False

        # blink detection
        self.blink_thresh = 0.23
        self._in_blink = False
        self._blink_start = 0.0
        self.consec_blinks = []
        self.last_click_time = 0.0
        self.show_click_anim = False
        self.click_anim_start = 0.0
        self.click_anim_duration = 0.35
        self.mouse_enabled = True

        atexit.register(self.cleanup)
        print("[INFO] EyecueAdvancedDualCalib initialized (mirror: {})".format(self.mirror))
        print("Controls: ESC/Q = quit | C = recalibrate | M = toggle mouse")

    # ---- cleanup ----
    def cleanup(self):
        try:
            cv2.destroyAllWindows()
        except:
            pass

    # ---- small helpers ----
    def _lm_to_xy(self, lm, shape):
        return np.array([lm.x * shape[1], lm.y * shape[0]], dtype=np.float32)

    def _iris_mean(self, idxs, landmarks, shape):
        pts = []
        for i in idxs:
            lm = landmarks[i]
            pts.append([lm.x * shape[1], lm.y * shape[0]])
        return np.mean(pts, axis=0)

    def _ear(self, eye_idx, landmarks):
        try:
            pts = np.array([[landmarks[i].x, landmarks[i].y] for i in eye_idx])
            A = euclidean(pts[1], pts[5])
            B = euclidean(pts[2], pts[4])
            C = euclidean(pts[0], pts[3])
            return (A + B) / (2.0 * C) if C > 0 else 0.3
        except Exception:
            return 0.3

    # ---- mirror-aware index mapping ----
    def _indices_for_current(self):
        if self.mirror:
            LEFT_IRIS = self.RIGHT_IRIS
            RIGHT_IRIS = self.LEFT_IRIS
            LEFT_CENTER = self.RIGHT_CENTER
            RIGHT_CENTER = self.LEFT_CENTER
            LEFT_EYE_IDX = self.RIGHT_EYE_IDX
            RIGHT_EYE_IDX = self.LEFT_EYE_IDX
        else:
            LEFT_IRIS = self.LEFT_IRIS
            RIGHT_IRIS = self.RIGHT_IRIS
            LEFT_CENTER = self.LEFT_CENTER
            RIGHT_CENTER = self.RIGHT_CENTER
            LEFT_EYE_IDX = self.LEFT_EYE_IDX
            RIGHT_EYE_IDX = self.RIGHT_EYE_IDX

        return LEFT_IRIS, RIGHT_IRIS, LEFT_CENTER, RIGHT_CENTER, LEFT_EYE_IDX, RIGHT_EYE_IDX

    # ---- feature extraction ----
    def extract_features(self, landmarks, frame_shape):
        """
        Build a 16-dim feature vector:
         l_iris_norm(2), r_iris_norm(2),
         l_iris_rel(2), r_iris_rel(2),
         inter(2), left_ear,right_ear (2),
         avg_eye_center_y_norm, eye_center_y_diff_norm (2),
         avg_vec (2)
        """
        try:
            LEFT_IRIS, RIGHT_IRIS, LEFT_CENTER, RIGHT_CENTER, LEFT_EYE_IDX, RIGHT_EYE_IDX = self._indices_for_current()

            l_iris = self._iris_mean(LEFT_IRIS, landmarks, frame_shape)
            r_iris = self._iris_mean(RIGHT_IRIS, landmarks, frame_shape)
            l_center = self._lm_to_xy(landmarks[LEFT_CENTER], frame_shape)
            r_center = self._lm_to_xy(landmarks[RIGHT_CENTER], frame_shape)

            # eye corners for widths (frame labeling)
            l_corner_l = self._lm_to_xy(landmarks[33], frame_shape)
            l_corner_r = self._lm_to_xy(landmarks[133], frame_shape)
            r_corner_l = self._lm_to_xy(landmarks[362], frame_shape)
            r_corner_r = self._lm_to_xy(landmarks[263], frame_shape)

            l_width = max(1.0, np.linalg.norm(l_corner_r - l_corner_l))
            r_width = max(1.0, np.linalg.norm(r_corner_r - r_corner_l))
            ipd = max(1.0, np.linalg.norm(l_center - r_center))

            mid = (l_center + r_center) / 2.0

            l_iris_norm = (l_iris - mid) / ipd
            r_iris_norm = (r_iris - mid) / ipd

            l_iris_rel = (l_iris - l_center) / l_width
            r_iris_rel = (r_iris - r_center) / r_width

            inter = (l_iris - r_iris) / ipd

            left_ear = self._ear(LEFT_EYE_IDX, landmarks)
            right_ear = self._ear(RIGHT_EYE_IDX, landmarks)

            avg_eye_center_y_norm = ((l_center[1] + r_center[1]) / 2.0 - mid[1]) / ipd
            eye_center_y_diff_norm = (l_center[1] - r_center[1]) / ipd

            l_vec = (l_iris - l_center) / ipd
            r_vec = (r_iris - r_center) / ipd
            avg_vec = (l_vec + r_vec) / 2.0

            feats = np.concatenate([
                l_iris_norm, r_iris_norm,
                l_iris_rel, r_iris_rel,
                inter,
                [left_ear, right_ear],
                [avg_eye_center_y_norm, eye_center_y_diff_norm],
                avg_vec
            ]).astype(np.float32)

            if feats.size < 16:
                feats = np.pad(feats, (0, 16 - feats.size), 'constant')

            return feats
        except Exception:
            return np.zeros(16, dtype=np.float32)

    # ---- geometric baseline estimate ----
    def compute_geom_prediction(self, features):
        try:
            f = features
            l_norm_x, l_norm_y, r_norm_x, r_norm_y = f[0], f[1], f[2], f[3]
            inter_x, inter_y = f[8], f[9]
            avg_eye_center_y_norm = f[12]
            avg_vec_x, avg_vec_y = f[14], f[15]

            horiz_signal = (l_norm_x + r_norm_x) * 0.5 + avg_vec_x * 0.8 + inter_x * 0.2
            vert_signal = (l_norm_y + r_norm_y) * 0.5 + avg_vec_y * 0.8 + avg_eye_center_y_norm * 0.6 + inter_y * 0.1

            raw_x = (0.5 + horiz_signal) * self.screen_w
            raw_y = (0.5 + vert_signal) * self.screen_h

            raw_x = float(np.clip(raw_x, 0, self.screen_w))
            raw_y = float(np.clip(raw_y, 0, self.screen_h))
            return np.array([raw_x, raw_y], dtype=np.float32)
        except Exception:
            return np.array([self.screen_w / 2.0, self.screen_h / 2.0], dtype=np.float32)

    # ---- blink detection & clicking ----
    def detect_blink_click(self, landmarks, frame_shape):
        LEFT_IRIS, RIGHT_IRIS, LEFT_CENTER, RIGHT_CENTER, L_IDX, R_IDX = self._indices_for_current()
        left_ear = self._ear(L_IDX, landmarks)
        right_ear = self._ear(R_IDX, landmarks)
        avg = (left_ear + right_ear) / 2.0
        t = time.time()
        clicked = False
        if avg < self.blink_thresh:
            if not self._in_blink:
                self._in_blink = True
                self._blink_start = t
        else:
            if self._in_blink:
                self._in_blink = False
                dur = t - self._blink_start
                if 0.06 < dur < 0.6:
                    self.consec_blinks.append(t)
                    self.consec_blinks = [tb for tb in self.consec_blinks if t - tb < 0.8]
                    if len(self.consec_blinks) >= 2 and (t - self.last_click_time) > 0.9:
                        try:
                            pyautogui.click()
                            clicked = True
                            self.last_click_time = t
                            self.show_click_anim = True
                            self.click_anim_start = t
                            print("[CLICK] double blink -> left click")
                        except Exception:
                            pass
                        self.consec_blinks = []
        return avg, clicked

    # ---- grid calibration (9 points) using queues/deques ----
    def calibrate_grid(self, cap):
        points = [
            (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
            (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
            (0.1, 0.9), (0.5, 0.9), (0.9, 0.9)
        ]
        # deques to store aggregated point-level data
        collected_feats = []
        collected_targets = []

        print("[CAL] Grid calibration: look at each red dot and press SPACE when ready.")
        root = tk.Tk()
        root.title("Eyecue Grid Calibration")
        root.attributes('-fullscreen', True)
        root.configure(bg='black')
        canvas = tk.Canvas(root, bg='black', highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        # Small preview window to show webcam + iris center while collecting (helps user see detection)
        PREVIEW_WIN = "Calibration Preview"
        cv2.namedWindow(PREVIEW_WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(PREVIEW_WIN, 480, 360)

        current = {'i': 0}
        def draw_dot(i):
            canvas.delete('all')
            sx = int(points[i][0] * self.screen_w)
            sy = int(points[i][1] * self.screen_h)
            canvas.create_oval(sx-30, sy-30, sx+30, sy+30, fill='red', outline='white', width=2)
            canvas.create_text(self.screen_w//2, 30, text=f"Look at dot {i+1}/9 and press SPACE", fill='white', font=('Arial', 18))
            root.update()

        def collect_samples(i):
            buf = []
            start = time.time()
            while (time.time() - start) < MAX_CAL_POINT_TIME:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue
                # show mirrored preview if mirror True
                preview_frame = frame.copy()
                if self.mirror:
                    preview_frame = cv2.flip(preview_frame, 1)
                # small preview overlay text
                cv2.putText(preview_frame, f"Point {i+1}/9 - Hold gaze", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)

                # process landmarks
                frame_rgb = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
                res = self.face_mesh.process(frame_rgb)
                iris_center = None
                if res.multi_face_landmarks:
                    lm = res.multi_face_landmarks[0].landmark
                    # compute iris mean (left/right indices are already mirror-aware in extract_features)
                    LEFT_IRIS, RIGHT_IRIS, _, _, _, _ = self._indices_for_current()
                    try:
                        l_iris = np.mean([[lm[idx].x * preview_frame.shape[1], lm[idx].y * preview_frame.shape[0]] for idx in LEFT_IRIS], axis=0)
                        r_iris = np.mean([[lm[idx].x * preview_frame.shape[1], lm[idx].y * preview_frame.shape[0]] for idx in RIGHT_IRIS], axis=0)
                        iris_center = ((l_iris + r_iris) / 2.0).astype(int)
                        # draw small green dot where iris center is detected
                        cv2.circle(preview_frame, (int(iris_center[0]), int(iris_center[1])), 6, (0, 255, 0), -1)
                    except Exception:
                        iris_center = None

                    # compute full features and append if valid
                    feats = self.extract_features(lm, preview_frame.shape)
                    if np.any(feats):
                        geom = self.compute_geom_prediction(feats)
                        sample = np.concatenate([feats, geom / np.array([self.screen_w, self.screen_h])])
                        buf.append(sample)

                # show preview (so user can see tracking)
                try:
                    cv2.imshow(PREVIEW_WIN, preview_frame)
                    cv2.waitKey(1)
                except Exception:
                    pass

                if len(buf) >= SAMPLES_PER_POINT:
                    break
            return np.array(buf)

        def on_key(event):
            i = current['i']
            if event.keysym == 'space':
                print(f"[CAL] Collecting for grid point {i+1}...")
                samples = collect_samples(i)
                if samples.shape[0] < max(6, SAMPLES_PER_POINT//2):
                    print("[CAL] Not enough samples collected for this point. Try again (more stable lighting / hold still).")
                    return
                # outlier removal median+MAD
                med = np.median(samples, axis=0)
                mad = np.median(np.abs(samples - med), axis=0) + 1e-8
                dev = np.max(np.abs(samples - med) / mad, axis=1)
                keep = samples[dev <= OUTLIER_MAD_THRESH]
                if keep.shape[0] < max(6, SAMPLES_PER_POINT//3):
                    print("[CAL] Too many outliers; retry this point.")
                    return
                agg = np.median(keep, axis=0)
                feats_agg = agg[:16]
                geom_norm = agg[16:18]
                tx = points[i][0] * self.screen_w
                ty = points[i][1] * self.screen_h
                if self.mirror:
                    tx = self.screen_w - tx
                collected_feats.append(np.concatenate([feats_agg, geom_norm]))
                collected_targets.append([tx, ty])
                current['i'] += 1
                if current['i'] >= len(points):
                    # done
                    root.destroy()
                    try:
                        cv2.destroyWindow(PREVIEW_WIN)
                    except:
                        pass
                    print("[CAL] Grid points collected.")
                else:
                    draw_dot(current['i'])
            elif event.keysym == 'Escape':
                root.destroy()
                try:
                    cv2.destroyWindow(PREVIEW_WIN)
                except:
                    pass
                print("[CAL] Grid cancelled by user.")

        draw_dot(0)
        root.bind("<KeyPress>", on_key)
        root.focus_set()
        try:
            root.mainloop()
        except Exception as e:
            print("[CAL] Grid UI error:", e)
            traceback.print_exc()
            try:
                cv2.destroyWindow(PREVIEW_WIN)
            except:
                pass

        # make safe numpy arrays (if nothing collected produce empty arrays)
        X = np.array(collected_feats) if len(collected_feats) > 0 else np.zeros((0, 18), dtype=np.float32)
        Y = np.array(collected_targets) if len(collected_targets) > 0 else np.zeros((0, 2), dtype=np.float32)
        return X, Y

    # ---- moving cursor calibration (automatic) ----
    def moving_cursor_calibration(self, cap, duration=MOVING_CAL_DURATION,
                                  sampling_rate=MOVING_CAL_SAMPLING_RATE, path_type=MOVING_PATH_TYPE):
        print("[CAL] Starting moving-cursor calibration. Follow the blue dot with your eyes.")
        root = tk.Tk()
        root.title("Eyecue Moving Cursor Calibration")
        root.attributes('-fullscreen', True)
        root.configure(bg='black')
        canvas = tk.Canvas(root, bg='black', highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        pts = []
        steps = max(2, int(duration * sampling_rate))
        if path_type == "line":
            for t in range(steps):
                frac = (t / (steps - 1))
                x = 0.05 + 0.9 * frac
                y = 0.5
                pts.append((x * self.screen_w, y * self.screen_h))
        elif path_type == "spiral":
            cx, cy = 0.5 * self.screen_w, 0.5 * self.screen_h
            max_r = min(self.screen_w, self.screen_h) * 0.45
            for t in range(steps):
                theta = 2.0 * math.pi * (t / max(1, steps))
                r = max_r * (t / steps)
                x = cx + r * math.cos(theta)
                y = cy + r * math.sin(theta)
                pts.append((float(np.clip(x, 0, self.screen_w)), float(np.clip(y, 0, self.screen_h))))
        else:  # zigzag
            rows = max(2, int(math.sqrt(steps)))
            cols = rows
            xs = np.linspace(0.1, 0.9, cols)
            ys = np.linspace(0.1, 0.9, rows)
            seq = []
            for j, y in enumerate(ys):
                row_xs = xs if j % 2 == 0 else xs[::-1]
                for x in row_xs:
                    seq.append((x, y))
            seq_full = []
            while len(seq_full) < steps:
                seq_full.extend(seq)
            for t in range(steps):
                x, y = seq_full[t]
                pts.append((x * self.screen_w, y * self.screen_h))

        collected = []
        targets = []
        start = time.time()
        frame_interval = 1.0 / sampling_rate
        try:
            while time.time() - start < duration:
                now = time.time() - start
                idx = int(min(len(pts) - 1, (now / duration) * len(pts)))
                tx, ty = pts[idx]
                # show blue dot
                canvas.delete("all")
                canvas.create_oval(int(tx)-24, int(ty)-24, int(tx)+24, int(ty)+24, fill='blue', outline='white', width=2)
                canvas.create_text(self.screen_w//2, 36, text="Follow the blue dot with your eyes", fill='white', font=('Arial', 18))
                root.update()

                t0 = time.time()
                # capture frames until next interval
                while time.time() - t0 < frame_interval:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        time.sleep(0.005)
                        continue
                    if self.mirror:
                        frame = cv2.flip(frame, 1)
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    res = self.face_mesh.process(frame_rgb)
                    if not res.multi_face_landmarks:
                        continue
                    lm = res.multi_face_landmarks[0].landmark
                    feats = self.extract_features(lm, frame.shape)
                    if not np.any(feats):
                        continue
                    geom = self.compute_geom_prediction(feats)
                    sample = np.concatenate([feats, geom / np.array([self.screen_w, self.screen_h])])
                    collected.append(sample)
                    ttx, tty = float(tx), float(ty)
                    if self.mirror:
                        ttx = self.screen_w - ttx
                    targets.append([ttx, tty])
                # let other threads / UI breathe
                time.sleep(0.001)
            root.destroy()
        except Exception as e:
            print("[CAL] Moving cursor UI loop exception:", e)
            traceback.print_exc()
            try:
                root.destroy()
            except:
                pass

        collected = np.array(collected) if len(collected) > 0 else np.zeros((0, 18), dtype=np.float32)
        targets = np.array(targets) if len(targets) > 0 else np.zeros((0, 2), dtype=np.float32)
        print(f"[CAL] Moving cursor samples collected: {collected.shape[0]}")
        return collected, targets

    # ---- unified calibration: grid then moving cursor ----
    def calibrate(self, cap):
        print("[INFO] Starting calibration (grid then moving cursor).")
        # Step 1: grid
        grid_X, grid_Y = self.calibrate_grid(cap)
        if grid_X.shape[0] < 1:
            print("[CAL] Grid calibration collected no valid data; aborting calibration.")
            return False

        # Step 2: moving cursor automatically runs
        move_X, move_Y = self.moving_cursor_calibration(cap,
                                                        duration=MOVING_CAL_DURATION,
                                                        sampling_rate=MOVING_CAL_SAMPLING_RATE,
                                                        path_type=MOVING_PATH_TYPE)

        if move_X.shape[0] < MOVING_CAL_MIN_SAMPLES:
            print("[CAL] Warning: moving-cursor collected few samples -> using grid-only dataset.")
            X_aug = grid_X
            Y = grid_Y
        else:
            X_aug = np.vstack([grid_X, move_X])
            Y = np.vstack([grid_Y, move_Y])

        if X_aug.shape[0] < MIN_CAL_POINTS:
            print("[CAL] Not enough combined calibration samples.")
            return False

        # global outlier rejection
        med = np.median(X_aug, axis=0)
        mad = np.median(np.abs(X_aug - med), axis=0) + 1e-8
        dev = np.max(np.abs(X_aug - med) / mad, axis=1)
        keep_mask = dev <= (OUTLIER_MAD_THRESH * 1.5)
        X_final = X_aug[keep_mask]
        Y_final = Y[keep_mask]

        print(f"[CAL] Combined calibration samples retained: {X_final.shape[0]}")
        self._train_and_postprocess(X_final, Y_final)
        return True

    # ---- train & heavy post-calibration processing ----
    def _train_and_postprocess(self, feats_aug, targets):
        # feats_aug shape: N x 18 (16 feats + 2 geom_norm)
        if feats_aug.shape[0] < 1:
            print("[TRAIN] No training data provided.")
            return

        X_raw = feats_aug[:, :16]
        X_geom = feats_aug[:, 16:18]
        X_combined = np.hstack([X_raw, X_geom])  # N x 18

        # scale + train
        self.scaler = StandardScaler()
        Xs = self.scaler.fit_transform(X_combined)

        yx = targets[:, 0]
        yy = targets[:, 1]

        try:
            self.ridge_x.fit(Xs, yx)
            self.ridge_y.fit(Xs, yy)
        except Exception as e:
            print("[TRAIN] Ridge training error:", e)

        try:
            self.global_x.fit(Xs, yx)
            self.global_y.fit(Xs, yy)
        except Exception as e:
            print("[TRAIN] ExtraTrees training error:", e)

        pred_x = self.global_x.predict(Xs)
        pred_y = self.global_y.predict(Xs)
        residuals_x = yx - pred_x
        residuals_y = yy - pred_y

        try:
            self.knn_res_x.fit(Xs, residuals_x)
            self.knn_res_y.fit(Xs, residuals_y)
        except Exception as e:
            print("[TRAIN] KNN residual training error:", e)

        try:
            corrected_pred_x = pred_x + self.knn_res_x.predict(Xs)
            corrected_pred_y = pred_y + self.knn_res_y.predict(Xs)
            rmse = math.sqrt(mean_squared_error(np.vstack([yx, yy]).T,
                                                np.vstack([corrected_pred_x, corrected_pred_y]).T))
            print(f"[TRAIN] Calibration RMSE (combined) = {rmse:.2f} px")
        except Exception:
            pass

        # feature importances
        try:
            fx = self.global_x.feature_importances_
            fy = self.global_y.feature_importances_
            importance = (fx + fy) / 2.0
            idxs = np.argsort(importance)[::-1][:6]
            print("[TRAIN] Top feature indices (0..17):", idxs.tolist())
            print("[TRAIN] Top importances:", importance[idxs].round(4).tolist())
        except Exception:
            pass

        self.is_calibrated = True
        print("[TRAIN] Post-processing complete. Models ready for runtime.")

    # ---- prediction pipeline ----
    def predict(self, features):
        if not self.is_calibrated:
            return None, None
        geom = self.compute_geom_prediction(features)  # absolute px
        geom_norm = geom / np.array([self.screen_w, self.screen_h])
        X_aug = np.concatenate([features, geom_norm])
        try:
            Xs = self.scaler.transform([X_aug])
        except Exception:
            # fallback: scaler not fitted
            return None, None
        try:
            x_global = float(self.global_x.predict(Xs)[0])
            y_global = float(self.global_y.predict(Xs)[0])
        except Exception:
            # fallback to ridge if ExtraTrees fails
            x_global = float(self.ridge_x.predict(Xs)[0]) if hasattr(self.ridge_x, 'coef_') else float(self.screen_w / 2.0)
            y_global = float(self.ridge_y.predict(Xs)[0]) if hasattr(self.ridge_y, 'coef_') else float(self.screen_h / 2.0)

        try:
            res_x = float(self.knn_res_x.predict(Xs)[0])
            res_y = float(self.knn_res_y.predict(Xs)[0])
        except Exception:
            res_x, res_y = 0.0, 0.0

        x_corr = float(np.clip(x_global + res_x, 0, self.screen_w))
        y_corr = float(np.clip(y_global + res_y, 0, self.screen_h))
        return x_corr, y_corr

    # ---- smoothing + apply (calls pyautogui) ----
    def smooth_and_apply(self, x, y):
        if x is None or y is None:
            return int(self.last_x), int(self.last_y)
        sx = (1 - EXP_SMOOTH) * self.last_x + EXP_SMOOTH * x
        sy = (1 - EXP_SMOOTH) * self.last_y + EXP_SMOOTH * y
        self.last_x, self.last_y = sx, sy
        if self.mouse_enabled:
            try:
                pyautogui.moveTo(int(round(sx)), int(round(sy)))
            except Exception:
                pass
        return int(round(sx)), int(round(sy))

    # ---- camera helpers (prefer external webcams; fallback to any available) ----
    def list_cameras(self, max_index=8):
        out = []
        for i in range(max_index + 1):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
            if cap is None:
                continue
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    out.append(i)
                cap.release()
        return out

    def open_best_camera(self, max_index=8):
        # Try external indices first (higher index), then 0
        for i in reversed(range(max_index + 1)):
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
            except Exception:
                cap = None
            if not cap or not cap.isOpened():
                try:
                    if cap:
                        cap.release()
                except:
                    pass
                continue
            ret, frame = cap.read()
            if ret and frame is not None:
                # set desired size
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
                cap.set(cv2.CAP_PROP_FPS, FPS_TARGET)
                print(f"[CAM] Using camera index {i}")
                return cap, i
            try:
                cap.release()
            except:
                pass
        return None, None

    # ---- main loop ----
    def run(self, max_camera_index=8, list_cams=False):
        if list_cams:
            cams = self.list_cameras(max_camera_index)
            print("[CAM LIST]", cams)
            return

        cap, idx = self.open_best_camera(max_camera_index)
        if cap is None:
            print("[ERROR] No camera found. Try plugging a webcam or increasing --max-camera.")
            return

        print("[INFO] Starting calibration")
        ok = self.calibrate(cap)
        if not ok or not self.is_calibrated:
            print("[ERROR] Calibration failed or was cancelled; exiting.")
            try:
                cap.release()
            except:
                pass
            return

        cv2.namedWindow("EyecueAdvanced", cv2.WINDOW_NORMAL)
        self.running = True
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue
                disp = frame.copy()
                if self.mirror:
                    disp = cv2.flip(disp, 1)
                frame_rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
                res = self.face_mesh.process(frame_rgb)
                if res.multi_face_landmarks:
                    lm = res.multi_face_landmarks[0].landmark
                    feats = self.extract_features(lm, disp.shape)
                    x_px, y_px = self.predict(feats)
                    sx, sy = self.smooth_and_apply(x_px, y_px)
                    self.detect_blink_click(lm, disp.shape)

                    cam_x = int(sx * (disp.shape[1] / float(self.screen_w)))
                    cam_y = int(sy * (disp.shape[0] / float(self.screen_h)))
                    cv2.drawMarker(disp, (cam_x, cam_y), (0, 255, 255), markerType=cv2.MARKER_CROSS, thickness=2)
                else:
                    cv2.putText(disp, "NO FACE/EYES", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)

                if self.show_click_anim and (time.time() - self.click_anim_start) < self.click_anim_duration:
                    alpha = 1.0 - (time.time() - self.click_anim_start) / self.click_anim_duration
                    radius = int(30 * (1.0 + 0.8 * (1 - alpha)))
                    cv2.circle(disp, (disp.shape[1]//2, disp.shape[0]//2), radius, (0,255,255), 3)
                else:
                    self.show_click_anim = False

                cv2.putText(disp, f"Mouse: {'ON' if self.mouse_enabled else 'OFF'} | Calibrated: {self.is_calibrated}", (10, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
                cv2.imshow("EyecueAdvanced", disp)

                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    print("[INFO] Quit requested")
                    break
                elif key == ord('m'):
                    self.mouse_enabled = not self.mouse_enabled
                    print("[INFO] Mouse toggled:", 'ON' if self.mouse_enabled else 'OFF')
                elif key == ord('c'):
                    print("[INFO] Recalibration requested")
                    try:
                        cap.release()
                    except:
                        pass
                    cv2.destroyAllWindows()
                    cap2 = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                    if cap2 and cap2.isOpened():
                        cap2.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W); cap2.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H); cap2.set(cv2.CAP_PROP_FPS, FPS_TARGET)
                        ok2 = self.calibrate(cap2)
                        cap2.release()
                        if not ok2:
                            print("[ERROR] Recalibration failed")
                            break
                        cap, idx = self.open_best_camera(max_camera_index)
                        if cap is None:
                            print("[ERROR] Camera lost after calibration")
                            break
                        cv2.namedWindow("EyecueAdvanced", cv2.WINDOW_NORMAL)
                    else:
                        print("[ERROR] Could not reopen camera for calibration")
                        break

        except KeyboardInterrupt:
            print("[INFO] Interrupted by user")
        except Exception as e:
            traceback.print_exc()
        finally:
            self.running = False
            try:
                cap.release()
            except:
                pass
            cv2.destroyAllWindows()

# ---- CLI ----
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--no-mirror', dest='mirror', action='store_false', help='disable horizontal mirroring')
    p.add_argument('--max-camera', '-m', type=int, default=8, help='max camera index to probe')
    p.add_argument('--list-cams', '-l', action='store_true', help='list cameras and exit')
    p.add_argument('--path', type=str, default=MOVING_PATH_TYPE, choices=['zigzag','line','spiral'], help='moving cursor path type')
    return p.parse_args()

def main():
    args = parse_args()
    tracker = EyecueAdvancedDualCalib(mirror=args.mirror)
    global MOVING_PATH_TYPE
    MOVING_PATH_TYPE = args.path
    if args.list_cams:
        print("[CAM LIST]", tracker.list_cameras(args.max_camera))
        return
    tracker.run(max_camera_index=args.max_camera)

if __name__ == '__main__':
    main()
