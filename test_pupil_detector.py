#!/usr/bin/env python3
"""
Simple test script for pupil_detector on laptop camera
"""

import cv2
import numpy as np
from pupil_detector import detect_pupil_contour

def main():
    """Test pupil detector on default laptop camera"""
    
    # Open default laptop camera
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print("[error] Could not open camera")
        return
    
    print("[info] Started pupil detector test. Press 'q' to exit.")
    
    try:
        while True:
            ret, frame = cap.read()
            
            if not ret:
                print("[error] Failed to read frame")
                break
            
            # Detect pupil (handle None or unexpected returns safely)
            result = detect_pupil_contour(frame)

            # Normalize unexpected return values
            if not result or (isinstance(result, tuple) and len(result) != 3):
                full_coords = roi_coords = bbox = None
            else:
                full_coords, roi_coords, bbox = result

            # Visualization
            if full_coords is not None:
                full_cx, full_cy = full_coords
                roi_cx, roi_cy = roi_coords
                w_box, h_box = bbox
                
                # Draw pupil center on frame
                cv2.circle(frame, (full_cx, full_cy), 5, (0, 255, 0), -1)
                cv2.circle(frame, (full_cx, full_cy), 15, (0, 255, 0), 2)
                
                # Draw bounding box
                h, w = frame.shape[:2]
                roi_x = int(w * 0.35)
                roi_y = int(h * 0.4)
                
                top_left = (roi_x + roi_cx - w_box // 2, roi_y + roi_cy - h_box // 2)
                bottom_right = (roi_x + roi_cx + w_box // 2, roi_y + roi_cy + h_box // 2)
                cv2.rectangle(frame, top_left, bottom_right, (255, 0, 0), 2)
                
                # Display coordinates
                text = f"Pupil: ({full_cx}, {full_cy})"
                cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                text = "No pupil detected"
                cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Draw ROI region
            h, w = frame.shape[:2]
            roi_top = int(h * 0.4)
            roi_bottom = int(h * 0.7)
            roi_left = int(w * 0.35)
            roi_right = int(w * 0.65)
            cv2.rectangle(frame, (roi_left, roi_top), (roi_right, roi_bottom), (255, 255, 0), 1)
            
            # Display
            cv2.imshow("Pupil Detector Test", frame)
            
            # Exit on 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[info] Test completed.")

if __name__ == "__main__":
    main()
