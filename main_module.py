#!/usr/bin/env python3
import cv2
import time
import numpy as np
from contour_gaze_tracker import ContourGazeTracker, ESP32CameraCapture
from CursorController import CursorController
from blink_detector import BlinkDetector
from autoscroll import autoscroll
from metrics_collector import MetricsCollector

def main():
    # --- Configuration ---
    # Set your ESP32 IP address or use 0 for default webcam
    camera_source = 0 # y"http://192.168.4.49/stream" # I.P. address running shell script
    screen_w, screen_h = 1920, 1080 # Update to your monitor resolution
    
    # --- Initialization ---
    # Initialize Gaze Tracker
    tracker = ContourGazeTracker(enable_metrics=True)
    
    # Initialize Cursor Controller with default calibration
    # (Values should ideally come from a calibration step)
    # placeholder values for left, right, top, bottom angles
    controller = CursorController(
        leftAngle=-15, rightAngle=15, topAngle=10, bottomAngle=-10,
        gyroH=0, gyroV=0, frameRate=30
    )
    
    # Initialize Blink Detector for click functionality
    blinker = BlinkDetector()
    
    # Setup Camera Capture (ESP32 or Webcam)
    if camera_source.startswith("http"):
        cap_source = ESP32CameraCapture(camera_source)
    else:
        cap_source = cv2.VideoCapture(int(camera_source))

    # State variables for autoscroll
    active_zone = None
    last_scroll = 0
    enter_t = time.time()

    print("[info] Starting Eyecue Main System...")
    
    try:
        while True:
            # 1. Capture Frame
            if isinstance(cap_source, ESP32CameraCapture):
                ret, frame = cap_source.read()
            else:
                ret, frame = cap_source.read()
            
            if not ret:
                continue

            # 2. Gaze Tracking & Pupil Detection
            # Processes the frame to get gaze angles (horizontal and vertical)
            gaze_data = tracker.process_frame(frame)
            
            if gaze_data['success']:
                angle_h = gaze_data['angle_h']
                angle_v = gaze_data['angle_v']
                pupil_y = gaze_data['pupil_center'][1]
                
                # 3. Update Cursor Position
                # Converts angles to screen coordinates
                # Assuming gyro data is 0 for now as integrated hardware varies
                controller.update_target(angle_h, angle_v, 0, 0)
                
                # 4. Handle Autoscroll
                # Logic to print or trigger scroll based on pupil position
                h, w, _ = frame.shape
                active_zone, last_scroll, enter_t = autoscroll(
                    height=h, 
                    current_y=pupil_y, 
                    enter_t=enter_t, 
                    last_scroll=last_scroll, 
                    active_zone=active_zone
                )

            # 5. Handle Blink Detection (Clicking)
            # Uses the blink detector to monitor for click triggers
            # Note: blink_detector.py UI requires a separate call or integration
            blinker.update(frame) 

            # 6. Visualization
            # Overlay tracking info on the frame for feedback
            tracker.draw_overlays(frame, gaze_data)
            cv2.imshow("Eyecue Integrated System", frame)

            # Exit on 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        # Cleanup
        if isinstance(cap_source, ESP32CameraCapture):
            cap_source.release()
        else:
            cap_source.release()
        cv2.destroyAllWindows()
        tracker.metrics.save_to_json() # Save performance stats
        print("[info] System shutdown.")

if __name__ == "__main__":
    main()