"""
9-point screen calibration for contour gaze: maps ROI-normalized pupil offsets
to monitor pixels via quadratic least squares. Offsets come from
ContourGazeTracker.extract_gaze_numbers()['single_offset'].
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

if TYPE_CHECKING:
    from contour_gaze_tracker import ContourGazeTracker

# Normalized screen targets (fraction of width / height), top-left origin — matches common 9-point layouts.
NINE_POINT_GRID: List[Tuple[float, float]] = [
    (0.1, 0.1),
    (0.5, 0.1),
    (0.9, 0.1),
    (0.1, 0.5),
    (0.5, 0.5),
    (0.9, 0.5),
    (0.1, 0.9),
    (0.5, 0.9),
    (0.9, 0.9),
]


def _design_row(fx: float, fy: float) -> np.ndarray:
    return np.array([1.0, fx, fy, fx * fx, fx * fy, fy * fy], dtype=np.float64)


class ContourGazeCalibrator:
    """
    Maps feature vector (offset_x, offset_y) to screen pixels using independent
    quadratic models for x and y (6 coefficients each), fitted with least squares.
    """

    def __init__(self) -> None:
        self.coef_x: Optional[np.ndarray] = None
        self.coef_y: Optional[np.ndarray] = None
        self.screen_width: int = 0
        self.screen_height: int = 0

    @property
    def is_fitted(self) -> bool:
        return self.coef_x is not None and self.coef_y is not None

    def fit(
        self,
        offset_x: np.ndarray,
        offset_y: np.ndarray,
        screen_x: np.ndarray,
        screen_y: np.ndarray,
        screen_width: int,
        screen_height: int,
    ) -> float:
        """Fit from arrays of shape (n,). Returns combined RMSE in pixels."""
        n = int(offset_x.shape[0])
        if n < 6:
            raise ValueError("need at least 6 calibration samples for quadratic fit")
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        A = np.stack([_design_row(float(offset_x[i]), float(offset_y[i])) for i in range(n)])
        sx = screen_x.astype(np.float64)
        sy = screen_y.astype(np.float64)
        self.coef_x, _, _, _ = np.linalg.lstsq(A, sx, rcond=None)
        self.coef_y, _, _, _ = np.linalg.lstsq(A, sy, rcond=None)
        pred_x = A @ self.coef_x
        pred_y = A @ self.coef_y
        rmse = float(np.sqrt(np.mean((pred_x - sx) ** 2 + (pred_y - sy) ** 2)))
        return rmse

    def map_offset_to_screen(self, offset_x: float, offset_y: float) -> Tuple[int, int]:
        if not self.is_fitted or self.coef_x is None or self.coef_y is None:
            raise RuntimeError("calibrator is not fitted")
        r = _design_row(float(offset_x), float(offset_y))
        x = float(r @ self.coef_x)
        y = float(r @ self.coef_y)
        xi = int(round(x))
        yi = int(round(y))
        xi = max(0, min(self.screen_width - 1, xi))
        yi = max(0, min(self.screen_height - 1, yi))
        return xi, yi

    def map_offset_to_screen_norm(self, offset_x: float, offset_y: float) -> Tuple[float, float]:
        """Screen position in [0, 1] x [0, 1] after mapping."""
        px, py = self.map_offset_to_screen(offset_x, offset_y)
        w = max(1, self.screen_width)
        h = max(1, self.screen_height)
        return px / w, py / h

    def to_dict(self) -> Dict[str, Any]:
        if not self.is_fitted or self.coef_x is None or self.coef_y is None:
            raise RuntimeError("calibrator is not fitted")
        return {
            "version": 1,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "coef_x": self.coef_x.tolist(),
            "coef_y": self.coef_y.tolist(),
        }

    def load_dict(self, data: Dict[str, Any]) -> None:
        if int(data.get("version", 1)) != 1:
            raise ValueError("unsupported calibration file version")
        self.screen_width = int(data["screen_width"])
        self.screen_height = int(data["screen_height"])
        self.coef_x = np.array(data["coef_x"], dtype=np.float64)
        self.coef_y = np.array(data["coef_y"], dtype=np.float64)

    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def load(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.load_dict(data)


def run_nine_point_calibration(
    tracker: ContourGazeTracker,
    *,
    cap,
    esp32_capture,
    is_local_camera: bool,
    save_path: str,
    samples_per_point: int = 28,
    max_seconds_per_point: float = 6.0,
) -> ContourGazeCalibrator:
    """
    Fullscreen Tk targets + OpenCV preview. User focuses each dot and presses SPACE
    to record median (offset_x, offset_y) for that screen location.
    """
    try:
        import tkinter as tk
    except ImportError as e:
        raise RuntimeError("tkinter is required for 9-point calibration") from e

    try:
        import pyautogui
    except ImportError as e:
        raise RuntimeError("pyautogui is required for screen size during calibration") from e

    from pupil_detector import detect_pupil_contour

    screen_w, screen_h = pyautogui.size()
    screen_w = int(screen_w)
    screen_h = int(screen_h)

    root = tk.Tk()
    root.title("Contour gaze — 9-point calibration")
    root.attributes("-fullscreen", True)
    root.configure(bg="black")
    canvas = tk.Canvas(root, bg="black", highlightthickness=0, highlightbackground="black", takefocus=True)
    canvas.pack(fill=tk.BOTH, expand=True)

    preview_win = "Calibration — camera"
    cv2_named = False

    def bring_calibration_to_front() -> None:
        """OpenCV steals focus on Windows; put the calibration layer back on top and give it keyboard focus."""
        root.lift()
        root.attributes("-topmost", True)
        root.update_idletasks()
        root.focus_force()
        canvas.focus_set()
        root.after(250, lambda: root.attributes("-topmost", False))

    def event_is_space(event: Any) -> bool:
        if event.keysym in ("space", "Space"):
            return True
        if getattr(event, "char", None) == " ":
            return True
        try:
            if int(event.keycode) == 32:
                return True
        except (TypeError, ValueError):
            pass
        return False

    def read_frame():
        if esp32_capture is not None:
            return esp32_capture.read()
        return cap.read()

    def preprocess(frame):
        if not is_local_camera or frame is None:
            return frame
        h, w = frame.shape[:2]
        crop_w = w // 8
        crop_h = h // 8
        cx = (w - crop_w) // 2
        cy = (h - crop_h) // 2
        cropped = frame[cy : cy + crop_h, cx : cx + crop_w]
        return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

    collected_fx: List[float] = []
    collected_fy: List[float] = []
    collected_sx: List[float] = []
    collected_sy: List[float] = []

    state: Dict[str, Any] = {"idx": 0, "done": False, "error": None, "busy": False}

    def draw_target(i: int) -> None:
        canvas.delete("all")
        nx, ny = NINE_POINT_GRID[i]
        sx = int(nx * screen_w)
        sy = int(ny * screen_h)
        r = max(12, min(screen_w, screen_h) // 40)
        canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill="red", outline="white", width=2)
        canvas.create_text(
            screen_w // 2,
            36,
            text=f"Point {i + 1} / 9 — look at the red dot",
            fill="white",
            font=("Arial", 18),
        )
        canvas.create_text(
            screen_w // 2,
            72,
            text="Press SPACE to record ~1 s of samples (camera window may pop up)",
            fill="white",
            font=("Arial", 14),
        )
        canvas.create_text(
            screen_w // 2,
            102,
            text="If SPACE does nothing: click this black screen once, then press SPACE",
            fill="#aaaaaa",
            font=("Arial", 12),
        )
        canvas.create_text(
            screen_w // 2,
            132,
            text="ESC to cancel",
            fill="#888888",
            font=("Arial", 12),
        )
        bring_calibration_to_front()
        root.update()

    def collect_one_point(i: int) -> Tuple[float, float]:
        nonlocal cv2_named
        buf_x: List[float] = []
        buf_y: List[float] = []
        t0 = time.time()
        min_needed = max(8, samples_per_point // 2)
        if not cv2_named:
            cv2.namedWindow(preview_win, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(preview_win, 480, 360)
            cv2_named = True

        while (time.time() - t0) < max_seconds_per_point:
            ret, frame = read_frame()
            if not ret or frame is None:
                time.sleep(0.01)
                root.update()
                continue
            frame = preprocess(frame)
            pupil_center, roi_center, _bbox = detect_pupil_contour(frame)
            if pupil_center is None:
                cv2.putText(
                    frame,
                    "No pupil — adjust lighting / position",
                    (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 0, 255),
                    2,
                )
                cv2.imshow(preview_win, frame)
                cv2.waitKey(1)
                root.update()
                continue
            gaze = tracker.extract_gaze_numbers(pupil_center, roi_center, frame.shape)
            if not gaze:
                root.update()
                continue
            ox, oy = gaze["single_offset"]
            buf_x.append(float(ox))
            buf_y.append(float(oy))
            cv2.circle(frame, pupil_center, 5, (0, 255, 0), -1)
            cv2.putText(
                frame,
                f"Samples: {len(buf_x)}/{samples_per_point}",
                (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )
            cv2.imshow(preview_win, frame)
            cv2.waitKey(1)
            root.update()
            if len(buf_x) >= samples_per_point:
                break
        if len(buf_x) < min_needed:
            try:
                cv2.destroyWindow(preview_win)
            except Exception:
                pass
            cv2_named = False
            bring_calibration_to_front()
            raise RuntimeError(f"too few gaze samples at point {i + 1} ({len(buf_x)}); try again")
        try:
            cv2.destroyWindow(preview_win)
        except Exception:
            pass
        cv2_named = False
        bring_calibration_to_front()
        return float(np.median(buf_x)), float(np.median(buf_y))

    def on_key(event) -> None:
        if state["done"] or state["busy"]:
            return
        if event.keysym == "Escape":
            state["error"] = "cancelled"
            state["done"] = True
            root.quit()
            return
        if not event_is_space(event):
            return
        state["busy"] = True
        try:
            i = state["idx"]
            try:
                fx, fy = collect_one_point(i)
            except Exception as ex:
                state["error"] = str(ex)
                state["done"] = True
                root.quit()
                return
            nx, ny = NINE_POINT_GRID[i]
            collected_fx.append(fx)
            collected_fy.append(fy)
            collected_sx.append(float(nx * screen_w))
            collected_sy.append(float(ny * screen_h))
            print(
                f"[cal] point {i + 1}/9: offset=({fx:.4f}, {fy:.4f}) -> screen=({collected_sx[-1]:.0f}, {collected_sy[-1]:.0f})"
            )
            if i + 1 >= len(NINE_POINT_GRID):
                state["done"] = True
                root.quit()
                return
            state["idx"] = i + 1
            draw_target(state["idx"])
        finally:
            state["busy"] = False

    canvas.bind("<Key>", on_key)
    draw_target(0)
    root.mainloop()
    root.destroy()

    try:
        cv2.destroyWindow(preview_win)
    except Exception:
        pass

    if state["error"]:
        if state["error"] == "cancelled":
            raise RuntimeError("calibration cancelled")
        raise RuntimeError(state["error"])

    cal = ContourGazeCalibrator()
    rmse = cal.fit(
        np.array(collected_fx, dtype=np.float64),
        np.array(collected_fy, dtype=np.float64),
        np.array(collected_sx, dtype=np.float64),
        np.array(collected_sy, dtype=np.float64),
        screen_w,
        screen_h,
    )
    print(f"[cal] fit RMSE (reprojection on calibration points): {rmse:.2f} px")
    cal.save(save_path)
    print(f"[cal] saved: {save_path}")
    return cal
