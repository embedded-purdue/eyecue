#!/usr/bin/env python3
"""
Simple contour-based blink detector
- uses pupil detection from contour_gaze_tracker.py
- counts blinks as absence of pupil
"""

import cv2
import numpy as np
import time
from collections import deque

class BlinkDetector:
    def __init__(self):
        self.frame_count = 0
        self.total_blinks = 0
        self.last_pupil_detected = True
        self.blink_debounce_frames = 0  # prevent double counting
        self.debounce_threshold = 0     # no debounce needed for contour tracking (absence of pupil)
        
        self.blink_queue = deque(maxlen=5)  # queue to track recent blink timestamps (max 5)
        self.double_blinks = 0              # count of double blinks detected
        self.triple_blinks = 0              # count of triple blinks detected
        

        self.BLINK_DURATION_MEAN = 0.202    # 202ms mean blink duration
        self.BLINK_DURATION_STD = 0.05      # ~50ms standard deviation
        
        # Research-backed timing thresholds for blink detection (based on Chen & Epps 2019)
        self.DOUBLE_BLINK_INTERVAL = 0.6    # 600ms max interval for double blinks (research-based)
        self.TRIPLE_BLINK_INTERVAL = 0.4    # 400ms max interval for triple blinks (research-based)
        self.TRIPLE_BLINK_TOTAL = 1.0       # 1000ms max total for triple blinks (research-based)
        self.PATTERN_TIMEOUT = 1.2          # 1200ms timeout to clear old blinks (research-based)
        
        # Precise timing state tracking
        self.blink_state = "idle"            # idle, waiting_for_second, waiting_for_third
        self.first_blink_time = 0            # timestamp of first blink
        self.second_blink_time = 0           # timestamp of second blink
        self.waiting_start_time = 0          # when we started waiting
        
        # blink detection balance - not too sensitive but detect absence of pupil
        self.blink_timestamps = []           # track all blink timestamps for accuracy
        self.last_blink_time = 0            # track last blink time for accuracy
        self.pupil_stability_frames = 0     # track consecutive frames with same pupil state
        self.stability_threshold = 2        # need 2 consistent frames for stable detection
        
        
        print("simple contour blink detector - press 'q' to quit")
        print("blink = no pupil detected")
        print("detects double and triple blinks with research-backed timing")

    def detect_pupil_contour(self, frame):
        """exact pupil detection from contour_gaze_tracker.py with smaller ROI"""
        # convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # crop roi ~ single eye area (smaller to avoid detecting both eyes)
        h, w = gray.shape
        roi = gray[int(h*0.45):int(h*0.65), int(w*0.4):int(w*0.6)]
        roi_color = frame[int(h*0.45):int(h*0.65), int(w*0.4):int(w*0.6)]
        
        # binarize -> pupil dark spot (exact same method as contour_gaze_tracker.py)
        thresh = cv2.adaptiveThreshold(
            roi, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            21, 10
        )
        
        # find contours (blobs)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # filter contours by size to ensure it's actually a pupil (not eyelid or other dark region)
            valid_contours = []
            for contour in contours:
                area = cv2.contourArea(contour)
                # pupil should be reasonably sized (not too big, not too small)
                if 50 < area < 1000:  # reasonable size range for pupil
                    valid_contours.append(contour)
            
            if valid_contours:
                # assume biggest valid blob = pupil
                pupil = max(valid_contours, key=cv2.contourArea)
                x, y, w_box, h_box = cv2.boundingRect(pupil)
                
                # calc center coords (relative to roi)
                cx = x + w_box // 2
                cy = y + h_box // 2
                
                # convert to full frame coords (corrected for smaller ROI)
                full_cx = cx + int(w*0.4)   # add roi offset (40% of width)
                full_cy = cy + int(h*0.45)  # add roi offset (45% of height)
                
                return (full_cx, full_cy), (cx, cy), (w_box, h_box)
        
        return None, None, None

    def detect_blink(self, frame):
        """stable blink detection - blink = no pupil detected with stability check"""
        pupil_center, roi_center, bbox = self.detect_pupil_contour(frame)
        
        # simple logic: if pupil was there before and now it's gone = blink
        pupil_detected = pupil_center is not None
        
        # balanced blink detection: not too sensitive but detect absence of pupil
        if self.last_pupil_detected and not pupil_detected:
            # pupil disappeared - check stability
            self.pupil_stability_frames += 1
            
            # only count as blink if stable for 2 frames (not too sensitive)
            if self.pupil_stability_frames >= self.stability_threshold:
                current_time = time.time()
                
                # prevent duplicate blinks within 150ms (less sensitive)
                if current_time - self.last_blink_time > 0.15:
                    self.blink_timestamps.append(current_time)
                    self.last_blink_time = current_time
                    print(f"BLINK DETECTED! Pupil disappeared at {current_time:.3f}s")
                    
                    # handle blink based on current state
                    if self.blink_state == "idle":
                        # first blink - start waiting for second
                        self.blink_state = "waiting_for_second"
                        self.first_blink_time = current_time
                        self.waiting_start_time = current_time
                        print(f"First blink detected - waiting for second blink...")
                    
                    elif self.blink_state == "waiting_for_second":
                        # second blink detected
                        interval = current_time - self.first_blink_time
                        if interval < self.DOUBLE_BLINK_INTERVAL:
                            # second blink within threshold - wait for third
                            self.blink_state = "waiting_for_third"
                            self.second_blink_time = current_time
                            self.waiting_start_time = current_time
                            print(f"Second blink detected - waiting for third blink...")
                        else:
                            # second blink too late - count first as single, start new pattern
                            self.total_blinks += 1
                            print(f"Single blink detected (second too late). Total: {self.total_blinks}")
                            self.blink_state = "idle"
                            self.first_blink_time = current_time
                            self.waiting_start_time = current_time
                            print(f"Starting new pattern with second blink...")
                            
                    elif self.blink_state == "waiting_for_third":
                        # third blink detected
                        interval = current_time - self.second_blink_time
                        total_time = current_time - self.first_blink_time
                        if interval < self.TRIPLE_BLINK_INTERVAL and total_time < self.TRIPLE_BLINK_TOTAL:
                            # triple blink detected
                            self.triple_blinks += 1
                            print(f"TRIPLE BLINK DETECTED! Total: {self.triple_blinks}")
                            self.blink_state = "idle"
                        else:
                            # third blink too late - count as double blink
                            self.double_blinks += 1
                            print(f"DOUBLE BLINK DETECTED! Total: {self.double_blinks}")
                            self.blink_state = "idle"
        
        elif not self.last_pupil_detected and pupil_detected:
            # pupil reappeared - reset stability counter
            self.pupil_stability_frames = 0
        
        elif self.last_pupil_detected and pupil_detected:
            # pupil still present - reset stability counter
            self.pupil_stability_frames = 0
        
        # check for timeouts on every frame (accuracy improvement)
        current_time = time.time()
        if self.blink_state == "waiting_for_second":
            if current_time - self.waiting_start_time >= self.DOUBLE_BLINK_INTERVAL:
                # timeout waiting for second blink - count as single
                print(f"Timeout waiting for second blink - counting as single blink")
                self.total_blinks += 1
                self.blink_state = "idle"
                
        elif self.blink_state == "waiting_for_third":
            if current_time - self.waiting_start_time >= self.TRIPLE_BLINK_INTERVAL:
                # timeout waiting for third blink - detect as double
                print(f"Timeout waiting for third blink - detecting as double blink")
                self.double_blinks += 1
                print(f"DOUBLE BLINK DETECTED! Total: {self.double_blinks}")
                print(f"  Interval: {self.second_blink_time - self.first_blink_time:.3f}s")
                self.blink_state = "idle"
        
        # accuracy improvement: cleanup old timestamps
        if len(self.blink_timestamps) > 10:
            self.blink_timestamps = self.blink_timestamps[-10:]  # keep only last 10 blinks
        
        self.last_pupil_detected = pupil_detected
        return pupil_detected, pupil_center

    def draw_ui_overlay(self, frame, pupil_detected, pupil_center):
        """draw simple blink counters and eye tracking area (FPS-independent)"""
        h, w = frame.shape[:2]
        
        # draw green box to show single eye tracking area (even smaller to avoid both eyes)
        roi_x1, roi_y1 = int(w*0.4), int(h*0.45)
        roi_x2, roi_y2 = int(w*0.6), int(h*0.65)
        cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 2)
        cv2.putText(frame, "SINGLE EYE AREA", (roi_x1, roi_y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # simple blink counters in top-left corner
        cv2.putText(frame, f"Single: {self.total_blinks}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Double: {self.double_blinks}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(frame, f"Triple: {self.triple_blinks}", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # show tracking status
        if pupil_detected and pupil_center:
            # draw pupil center
            cv2.circle(frame, pupil_center, 5, (0, 255, 0), -1)
            # show tracking status on screen
            cv2.putText(frame, "TRACKING: ACTIVE", (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        else:
            # show no tracking
            cv2.putText(frame, "TRACKING: NO PUPIL", (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        
        # quit instruction
        cv2.putText(frame, "Press 'q' to quit", (w-150, h-20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)




    def run(self, camera_index=0):
        """main blink detection loop"""
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            print(f"[error] could not open camera {camera_index}")
            return
        
        # set camera properties for robust contour gaze tracking (FPS-independent)
        # try to set resolution, but don't fail if camera doesn't support it
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimal buffer for real-time
        # Note: FPS is not set to work with any camera FPS
        
        # verify camera is still working after setting properties
        ret, test_frame = cap.read()
        if not ret:
            print("[warning] camera failed after setting properties, using default settings")
            cap.release()
            cap = cv2.VideoCapture(camera_index)
            if not cap.isOpened():
                print(f"[error] could not reopen camera {camera_index}")
                return

        print("[info] starting FPS-independent blink detection...")
        print(f"[info] camera: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {cap.get(cv2.CAP_PROP_FPS):.1f}fps")
        
        # time-based output for FPS independence
        last_output_time = time.time()
        output_interval = 2.0  # output every 2 seconds regardless of FPS
        
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[error] failed to read frame from camera")
                print("[info] trying to reinitialize camera...")
                cap.release()
                cap = cv2.VideoCapture(camera_index)
                if not cap.isOpened():
                    print("[error] could not reopen camera")
                    break
                continue
            
            self.frame_count += 1
            current_time = time.time()
            
            # detect blink
            pupil_detected, pupil_center = self.detect_blink(frame)
            
            
            # print every 2 seconds for FPS-independent performance
            if current_time - last_output_time >= output_interval:
                print(f"\n=== Time {current_time:.1f}s (Frame {self.frame_count}) ===")
                if pupil_detected:
                    print(f"Pupil detected at: {pupil_center}")
                else:
                    print("No pupil detected (potential blink)")
                    print("  This means: eye is closed, blinking, or no valid pupil found")
                print(f"Last pupil state: {self.last_pupil_detected}")
                print(f"Current pupil state: {pupil_detected}")
                print(f"Total blinks: {self.total_blinks}")
                print(f"Double blinks: {self.double_blinks}")
                print(f"Triple blinks: {self.triple_blinks}")
                print(f"Current state: {self.blink_state}")
                last_output_time = current_time
            
            # create comprehensive UI overlay
            self.draw_ui_overlay(frame, pupil_detected, pupil_center)
            
            # show frame
            cv2.imshow("Blink Detector", frame)
            
            # exit on 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        print("[info] blink detection stopped")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='contour-based blink detector')
    parser.add_argument('--camera', type=int, default=0, help='camera index')
    args = parser.parse_args()
    
    detector = BlinkDetector()
    detector.run(camera_index=args.camera)

if __name__ == "__main__":
    main()