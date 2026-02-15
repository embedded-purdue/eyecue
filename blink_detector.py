#!/usr/bin/env python3

import cv2
import numpy as np
import time
from collections import deque
from pupil_detector import detect_pupil_contour

class BlinkDetector:
    def __init__(self):
        self.frame_count = 0
        self.total_blinks = 0
        self.last_pupil_detected = True
        self.last_pupil_in_focus = False  # track previous focus state
        self.blink_debounce_frames = 0  # prevent double counting
        self.debounce_threshold = 0     # no debounce needed for contour tracking (absence of pupil)
        
        self.blink_queue = deque(maxlen=5)  # queue to track recent blink timestamps (max 5)
        self.double_blinks = 0              # count of double blinks detected
        self.triple_blinks = 0              # count of triple blinks detected
        
        # Focus tracking for pupil position
        self.focus_center = None            # center of focus area
        self.focus_radius = 60              # radius of focus area (pixels) - smaller for more sensitivity
        self.focused_frames = 0             # consecutive frames pupil was in focus
        self.focus_threshold = 5            # frames needed to establish focus - lower for faster response
        

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
        print("blink = pupil disappeared OR moved away from focus")
        print("sensitive to any movement away from focus area")
        print("detects double and triple blinks with research-backed timing")
        print(f"Timing thresholds:")
        print(f"  Double blink interval: {self.DOUBLE_BLINK_INTERVAL:.3f}s")
        print(f"  Triple blink interval: {self.TRIPLE_BLINK_INTERVAL:.3f}s")
        print(f"  Triple blink total: {self.TRIPLE_BLINK_TOTAL:.3f}s")
        print("Controls: 'q'=quit, 't'=test patterns, 'r'=reset state, 'f'=reset focus")

    def is_pupil_in_focus(self, pupil_center):
        """Check if pupil is within focus area"""
        if pupil_center is None or self.focus_center is None:
            return False
        
        # Calculate distance from focus center
        dx = pupil_center[0] - self.focus_center[0]
        dy = pupil_center[1] - self.focus_center[1]
        distance = (dx*dx + dy*dy)**0.5
        
        return distance <= self.focus_radius

    def update_focus_area(self, pupil_center):
        """Update focus area based on pupil position - keep focus area stable"""
        if pupil_center is not None:
            if self.focus_center is None:
                # Initialize focus area at first pupil detection
                self.focus_center = pupil_center
                self.focused_frames = 1
                print(f"Focus area initialized at: {pupil_center}")
            else:
                # Check if pupil is still in focus
                if self.is_pupil_in_focus(pupil_center):
                    self.focused_frames += 1
                    # Only update focus center if pupil has been stable for a while
                    if self.focused_frames > 30:  # after 30 frames of stability
                        # Very slow adjustment to follow gradual drift
                        alpha = 0.02  # much slower smoothing
                        self.focus_center = (
                            int(self.focus_center[0] * (1-alpha) + pupil_center[0] * alpha),
                            int(self.focus_center[1] * (1-alpha) + pupil_center[1] * alpha)
                        )
                else:
                    # Pupil moved out of focus - keep focus area fixed
                    # Don't reset focus area, let it stay where it was
                    pass


    def detect_blink(self, frame):
        """detect blink when pupil disappears OR moves away from focus"""
        pupil_center, bbox = detect_pupil_contour(frame)
        current_time = time.time()
        
        # Update focus area based on current pupil position
        self.update_focus_area(pupil_center)
        
        # Check if pupil is detected
        pupil_detected = pupil_center is not None
        pupil_in_focus = self.is_pupil_in_focus(pupil_center) if pupil_detected else False
        
        # Check for timeouts FIRST (before processing new blinks)
        self._check_timeouts(current_time)
        
        # Blink detection: track state changes
        blink_detected = False
        blink_reason = ""
        
        # Case 1: pupil disappeared (eyes closed)
        if self.last_pupil_detected and not pupil_detected:
            blink_detected = True
            blink_reason = "pupil disappeared"
        
        # Case 2: pupil was in focus, now moved away from focus
        elif (self.last_pupil_in_focus and pupil_detected and not pupil_in_focus):
            blink_detected = True
            blink_reason = "pupil moved away from focus"
        
        # Case 3: pupil was detected, now disappeared (backup check)
        elif (self.last_pupil_detected and not pupil_detected):
            blink_detected = True
            blink_reason = "pupil disappeared"
        
        if blink_detected:
            # prevent duplicate blinks within 100ms
            if current_time - self.last_blink_time > 0.1:
                self.blink_timestamps.append(current_time)
                self.last_blink_time = current_time
                print(f"BLINK DETECTED! {blink_reason} at {current_time:.3f}s")
                
                # handle blink based on current state
                self._process_blink_state(current_time)
        
        # Reset stability counter when pupil state changes
        if pupil_detected != self.last_pupil_detected:
            self.pupil_stability_frames = 0
        
        # accuracy improvement: cleanup old timestamps
        if len(self.blink_timestamps) > 10:
            self.blink_timestamps = self.blink_timestamps[-10:]  # keep only last 10 blinks
        
        # Update state tracking for next frame
        self.last_pupil_detected = pupil_detected
        self.last_pupil_in_focus = pupil_in_focus
        
        # Debug output every 30 frames to track state changes
        if self.frame_count % 30 == 0:
            print(f"Frame {self.frame_count}: pupil_detected={pupil_detected}, pupil_in_focus={pupil_in_focus}")
        
        return pupil_detected, pupil_center
    
    def _process_blink_state(self, current_time):
        """Process blink state transitions with comprehensive timing checks"""
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
                print(f"  Interval: {interval:.3f}s (threshold: {self.DOUBLE_BLINK_INTERVAL:.3f}s)")
            else:
                # second blink too late - count first as single, start new pattern
                self.total_blinks += 1
                print(f"Single blink detected (second too late). Total: {self.total_blinks}")
                print(f"  Interval: {interval:.3f}s (threshold: {self.DOUBLE_BLINK_INTERVAL:.3f}s)")
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
                print(f"  Interval: {interval:.3f}s (threshold: {self.TRIPLE_BLINK_INTERVAL:.3f}s)")
                print(f"  Total time: {total_time:.3f}s (threshold: {self.TRIPLE_BLINK_TOTAL:.3f}s)")
                self.blink_state = "idle"
            else:
                # third blink too late - count as double blink
                self.double_blinks += 1
                print(f"DOUBLE BLINK DETECTED! Total: {self.double_blinks}")
                print(f"  Interval: {interval:.3f}s (threshold: {self.TRIPLE_BLINK_INTERVAL:.3f}s)")
                print(f"  Total time: {total_time:.3f}s (threshold: {self.TRIPLE_BLINK_TOTAL:.3f}s)")
                self.blink_state = "idle"
    
    def _check_timeouts(self, current_time):
        """Check for timeouts in blink state machine"""
        if self.blink_state == "waiting_for_second":
            if current_time - self.waiting_start_time >= self.DOUBLE_BLINK_INTERVAL:
                # timeout waiting for second blink - count as single
                self.total_blinks += 1
                print(f"Timeout waiting for second blink - counting as single blink. Total: {self.total_blinks}")
                print(f"  Timeout after: {current_time - self.waiting_start_time:.3f}s")
                self.blink_state = "idle"
                
        elif self.blink_state == "waiting_for_third":
            if current_time - self.waiting_start_time >= self.TRIPLE_BLINK_INTERVAL:
                # timeout waiting for third blink - detect as double
                self.double_blinks += 1
                print(f"Timeout waiting for third blink - detecting as double blink. Total: {self.double_blinks}")
                print(f"  Timeout after: {current_time - self.waiting_start_time:.3f}s")
                print(f"  Double blink interval: {self.second_blink_time - self.first_blink_time:.3f}s")
                self.blink_state = "idle"
    
    def get_state_info(self):
        """Get current state information for debugging and testing"""
        current_time = time.time()
        return {
            'state': self.blink_state,
            'pupil_detected': self.last_pupil_detected,
            'stability_frames': self.pupil_stability_frames,
            'total_blinks': self.total_blinks,
            'double_blinks': self.double_blinks,
            'triple_blinks': self.triple_blinks,
            'first_blink_time': self.first_blink_time,
            'second_blink_time': self.second_blink_time,
            'waiting_start_time': self.waiting_start_time,
            'time_since_first': current_time - self.first_blink_time if self.first_blink_time > 0 else 0,
            'time_since_second': current_time - self.second_blink_time if self.second_blink_time > 0 else 0,
            'time_since_waiting': current_time - self.waiting_start_time if self.waiting_start_time > 0 else 0
        }
    
    def reset_state(self):
        """Reset blink detection state for testing"""
        self.blink_state = "idle"
        self.first_blink_time = 0
        self.second_blink_time = 0
        self.waiting_start_time = 0
        self.pupil_stability_frames = 0
        self.last_blink_time = 0
        print("Blink detection state reset")
    
    def reset_focus_area(self):
        """Reset focus area to current pupil position"""
        self.focus_center = None
        self.focused_frames = 0
        print("Focus area reset - will reinitialize on next pupil detection")
    
    def test_blink_patterns(self):
        """Test method to verify blink pattern detection"""
        print("\n=== Testing Blink Pattern Detection ===")
        print("Current state:", self.blink_state)
        print("Counts - Single:", self.total_blinks, "Double:", self.double_blinks, "Triple:", self.triple_blinks)
        
        if self.blink_state != "idle":
            state_info = self.get_state_info()
            print("State details:")
            print(f"  Time since first blink: {state_info['time_since_first']:.3f}s")
            print(f"  Time since second blink: {state_info['time_since_second']:.3f}s")
            print(f"  Time since waiting started: {state_info['time_since_waiting']:.3f}s")
        
        print("=== End Test ===\n")

    def draw_ui_overlay(self, frame, pupil_detected, pupil_center):
        """draw simple blink counters and eye tracking area (FPS-independent)"""
        h, w = frame.shape[:2]
        
        # draw green box to show pupil detection area (matches pupil_detector.py ROI)
        roi_x1, roi_y1 = int(w*0.35), int(h*0.4)
        roi_x2, roi_y2 = int(w*0.65), int(h*0.7)
        cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 2)
        cv2.putText(frame, "PUPIL DETECTION AREA", (roi_x1, roi_y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # draw focus area circle if established
        if self.focus_center is not None and self.focused_frames >= self.focus_threshold:
            cv2.circle(frame, self.focus_center, self.focus_radius, (0, 255, 255), 2)
            cv2.putText(frame, "FOCUS AREA", (self.focus_center[0]-40, self.focus_center[1]-self.focus_radius-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        # simple blink counters in top-left corner
        cv2.putText(frame, f"Single: {self.total_blinks}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Double: {self.double_blinks}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(frame, f"Triple: {self.triple_blinks}", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # show focus status
        if pupil_detected and pupil_center:
            # draw pupil center
            cv2.circle(frame, pupil_center, 5, (0, 255, 0), -1)
            # show focus status
            if self.is_pupil_in_focus(pupil_center):
                cv2.putText(frame, "IN FOCUS", (10, 120), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                cv2.putText(frame, "OUT OF FOCUS", (10, 120), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
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
            
            # handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('t'):
                # test blink patterns
                self.test_blink_patterns()
            elif key == ord('r'):
                # reset state
                self.reset_state()
            elif key == ord('f'):
                # reset focus area
                self.reset_focus_area()
        
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