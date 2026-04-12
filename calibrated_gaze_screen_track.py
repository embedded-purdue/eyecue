#!/usr/bin/env python3
"""
Calibrated pupil → screen mapping (official pipeline for this repo).

Pipeline
--------
1. ``detect_pupil_contour`` → pupil (x, y) in frame pixels.
2. ``ContourGazeTracker.extract_gaze_numbers`` → unit **gaze vector**, angles, ROI-normalized
   ``single_offset`` (f_x, f_y), and (if calibration JSON is loaded) **screen_px** / **screen_norm**
   from ``ContourGazeCalibrator`` quadratic fit on (f_x, f_y).
3. Rescale **screen_px** from calibration-time resolution to current monitor size, then
   ``CursorController.move_to_screen_pixels`` (instant jump; PyAutoGUI fail-safe is turned off so
   corner targets do not abort the run).

Requires ``contour_gaze_calibration.json`` from ``contour_gaze_tracker.py --calibrate-only`` (or
``--calibrate``), using the same camera framing (e.g. same webcam zoom) as calibration.

Usage
-----
  python calibrated_gaze_screen_track.py --camera 0
  python calibrated_gaze_screen_track.py --camera http://192.168.4.49/stream --calibration my_cal.json
  python calibrated_gaze_screen_track.py --camera 0 --no-cursor
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from contour_gaze_tracker import ContourGazeTracker, ESP32CameraCapture
from CursorController import CursorController
from pupil_detector import detect_pupil_contour


def _rescale_calibrated_px(sx, sy, out_w, out_h, cal_w, cal_h):
    cw = max(1, int(cal_w))
    ch = max(1, int(cal_h))
    ow = max(1, int(out_w))
    oh = max(1, int(out_h))
    nx = int(round(float(sx) * ow / cw))
    ny = int(round(float(sy) * oh / ch))
    return max(0, min(ow - 1, nx)), max(0, min(oh - 1, ny))


def _open_capture(camera_input):
    """Return (cap_source, is_esp32, is_local_camera) for frame loop."""
    is_esp32 = isinstance(camera_input, str) and camera_input.startswith("http://")
    if is_esp32:
        print(f"[info] ESP32 stream: {camera_input}")
        return ESP32CameraCapture(camera_input), True, False
    cap = cv2.VideoCapture(camera_input)
    if not cap.isOpened():
        raise RuntimeError(f"could not open camera/video: {camera_input}")
    is_local = isinstance(camera_input, int)
    if is_local:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        print("[info] local webcam — 8x center zoom (match calibration)")
    else:
        print(f"[info] video file: {camera_input}")
    return cap, False, is_local


def _read_frame(cap_source, is_esp32):
    if is_esp32:
        return cap_source.read()
    return cap_source.read()


def _release(cap_source, is_esp32):
    if is_esp32:
        cap_source.release()
    else:
        cap_source.release()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Track pupil → gaze vector → calibrated screen_px (9-point JSON mapping)."
    )
    parser.add_argument(
        "--camera",
        type=str,
        default="0",
        help="Webcam index (e.g. 0), video file path, or http:// ESP32 stream URL",
    )
    parser.add_argument(
        "--calibration",
        type=str,
        default=None,
        help="Path to contour_gaze_calibration.json (default: next to this script)",
    )
    parser.add_argument(
        "--no-cursor",
        action="store_true",
        help="Do not move the system cursor (only show overlays / print)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Nominal frame rate for CursorController movement smoothing",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    cal_path = args.calibration or str(repo_root / "contour_gaze_calibration.json")
    if not Path(cal_path).is_file():
        raise SystemExit(
            f"Calibration file not found: {cal_path}\n"
            "Run: python contour_gaze_tracker.py --calibrate-only --camera 0"
        )

    tracker = ContourGazeTracker(enable_metrics=False, calibration_path=cal_path)
    if not tracker.gaze_calibrator.is_fitted:
        raise SystemExit(f"Invalid or empty calibration: {cal_path}")

    try:
        camera_input = int(args.camera)
    except ValueError:
        camera_input = args.camera

    cap_source, is_esp32, is_local = _open_capture(camera_input)
    smoothing_alpha = 0.3
    smoothed_center = None
    controller = None
    if not args.no_cursor:
        controller = CursorController(
            leftAngle=-15,
            rightAngle=15,
            topAngle=10,
            bottomAngle=-10,
            gyroH=0,
            gyroV=0,
            frameRate=max(1, int(args.fps)),
        )

    print("[info] Calibrated gaze → screen (Ctrl+C or Q to quit)")
    print(f"[info] Calibration: {cal_path}")
    cal = tracker.gaze_calibrator
    print(f"[info] Calibrated for screen {cal.screen_width}x{cal.screen_height} px")

    frame_count = 0
    try:
        while True:
            ret, frame = _read_frame(cap_source, is_esp32)
            if not ret or frame is None:
                if is_esp32:
                    import time

                    time.sleep(0.05)
                    continue
                break

            if is_local and frame is not None:
                h, w = frame.shape[:2]
                crop_w = w // 8
                crop_h = h // 8
                cx = (w - crop_w) // 2
                cy = (h - crop_h) // 2
                frame = frame[cy : cy + crop_h, cx : cx + crop_w]
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)

            pupil_center, roi_center, _bbox = detect_pupil_contour(frame)
            if pupil_center is not None:
                if smoothed_center is None:
                    smoothed_center = pupil_center
                else:
                    a = smoothing_alpha
                    smoothed_center = (
                        int(a * pupil_center[0] + (1 - a) * smoothed_center[0]),
                        int(a * pupil_center[1] + (1 - a) * smoothed_center[1]),
                    )
            else:
                smoothed_center = None

            gaze_data = None
            if smoothed_center is not None:
                gaze_data = tracker.extract_gaze_numbers(smoothed_center, roi_center, frame.shape)

            if gaze_data is not None and gaze_data.get("screen_px") is not None:
                gx, gy, gz = gaze_data["single_gaze_vector"]
                ox, oy = gaze_data["single_offset"]
                spx, spy = gaze_data["screen_px"]
                snx, sny = gaze_data["screen_norm"]
                if controller is not None:
                    ow, oh = controller.screenWidth, controller.screenHeight
                    mx, my = _rescale_calibrated_px(spx, spy, ow, oh, cal.screen_width, cal.screen_height)
                    controller.move_to_screen_pixels(mx, my)

                frame_count += 1
                if frame_count % 15 == 0:
                    print(
                        f"gaze=[{gx:+.3f},{gy:+.3f},{gz:+.3f}] "
                        f"offset=({ox:+.3f},{oy:+.3f}) "
                        f"screen_px=({spx},{spy}) norm=({snx:.3f},{sny:.3f})"
                    )

                fh = frame.shape[0]
                cv2.putText(
                    frame,
                    f"gvec z: {gz:.2f}  off: ({ox:.2f},{oy:.2f})",
                    (10, fh - 42),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (200, 200, 200),
                    1,
                )
                cv2.putText(
                    frame,
                    f"cal screen_px: ({spx}, {spy})  norm: ({snx:.2f},{sny:.2f})",
                    (10, fh - 22),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 200, 0),
                    2,
                )

            if pupil_center is not None:
                cv2.circle(frame, pupil_center, 3, (0, 0, 255), 2)
            if smoothed_center is not None:
                cv2.circle(frame, smoothed_center, 5, (0, 255, 0), -1)

            h, w = frame.shape[:2]
            roi_x1, roi_y1 = int(w * 0.2), int(h * 0.3)
            roi_x2, roi_y2 = int(w * 0.8), int(h * 0.8)
            cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 1)

            cv2.imshow("Calibrated gaze → screen", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    finally:
        _release(cap_source, is_esp32)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
