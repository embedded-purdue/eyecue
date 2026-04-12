#!/usr/bin/env python3
import time
import cv2
from pathlib import Path

from contour_gaze_tracker import ContourGazeTracker, ESP32CameraCapture
from pupil_detector import detect_pupil_contour
from CursorController import CursorController
from blink_detector import BlinkDetector
from autoscroll import autoscroll
from metrics_collector import MetricsCollector


def _rescale_calibrated_px(sx, sy, out_w, out_h, cal_w, cal_h):
    """Map calibration-resolution pixels to current logical screen size."""
    cw = max(1, int(cal_w))
    ch = max(1, int(cal_h))
    ow = max(1, int(out_w))
    oh = max(1, int(out_h))
    # Same as ContourPupilFrameProcessor: always scale (identity when dims match), int-round, clamp.
    nx = int(round(float(sx) * ow / cw))
    ny = int(round(float(sy) * oh / ch))
    return max(0, min(ow - 1, nx)), max(0, min(oh - 1, ny))


def main():
    # --- Configuration ---
    camera_source = "http://192.168.4.49/stream"  # ESP32 stream or "0" for webcam

    repo_root = Path(__file__).resolve().parent
    default_cal = repo_root / "contour_gaze_calibration.json"
    calibration_path = str(default_cal) if default_cal.is_file() else None

    tracker = ContourGazeTracker(enable_metrics=True, calibration_path=calibration_path)
    controller = CursorController(
        leftAngle=-15,
        rightAngle=15,
        topAngle=10,
        bottomAngle=-10,
        gyroH=0,
        gyroV=0,
        frameRate=30,
    )
    blinker = BlinkDetector()

    if camera_source.startswith("http"):
        cap_source = ESP32CameraCapture(camera_source)
    else:
        cap_source = cv2.VideoCapture(int(camera_source))

    active_zone = None
    last_scroll = 0
    enter_t = time.time()

    use_calibrated_cursor = tracker.gaze_calibrator.is_fitted
    if use_calibrated_cursor:
        print("[info] Using 9-point calibration for cursor (screen_px path).")
    else:
        print("[info] No calibration JSON found; cursor uses angle-based CursorController mapping.")
        print(f"[info] Expected calibration file: {default_cal}")

    print("[info] Starting Eyecue Main System...")

    try:
        while True:
            if isinstance(cap_source, ESP32CameraCapture):
                ret, frame = cap_source.read()
            else:
                ret, frame = cap_source.read()

            if not ret:
                continue

            h, w, _ = frame.shape
            t0 = time.time()
            pupil_center, roi_center, _bbox = detect_pupil_contour(frame)
            detection_time = time.time() - t0

            gaze_data = None
            if pupil_center is not None:
                gaze_data = tracker.extract_gaze_numbers(pupil_center, roi_center, frame.shape)

            if tracker.metrics:
                angles = tuple(gaze_data["single_angles"]) if gaze_data else None
                tracker.metrics.record_frame(pupil_center, detection_time, angles)

            if gaze_data is not None:
                out_w, out_h = controller.screenWidth, controller.screenHeight
                if use_calibrated_cursor and gaze_data.get("screen_px") is not None:
                    cal = tracker.gaze_calibrator
                    sx, sy = gaze_data["screen_px"]
                    mx, my = _rescale_calibrated_px(
                        sx, sy, out_w, out_h, cal.screen_width, cal.screen_height
                    )
                    controller.move_to_screen_pixels(mx, my)
                else:
                    angle_h, angle_v = gaze_data["single_angles"]
                    controller.update_target(angle_h, angle_v, 0, 0)

                pupil_y = pupil_center[1]
                active_zone, last_scroll, enter_t = autoscroll(
                    height=h,
                    current_y=pupil_y,
                    enter_t=enter_t,
                    last_scroll=last_scroll,
                    active_zone=active_zone,
                )

            if pupil_center is not None:
                cv2.circle(frame, pupil_center, 5, (0, 255, 0), -1)
            roi_x1, roi_y1 = int(w * 0.2), int(h * 0.3)
            roi_x2, roi_y2 = int(w * 0.8), int(h * 0.8)
            cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 1)
            if gaze_data and gaze_data.get("screen_px") is not None:
                spx, spy = gaze_data["screen_px"]
                cv2.putText(
                    frame,
                    f"cal px: ({spx},{spy})",
                    (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 200, 0),
                    1,
                )

            blinker.update(frame)
            cv2.imshow("Eyecue Integrated System", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        if isinstance(cap_source, ESP32CameraCapture):
            cap_source.release()
        else:
            cap_source.release()
        cv2.destroyAllWindows()
        if tracker.metrics:
            tracker.metrics.save_to_json()
        print("[info] System shutdown.")


if __name__ == "__main__":
    main()
