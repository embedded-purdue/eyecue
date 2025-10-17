#!/usr/bin/env python3
"""
contour-based gaze tracker
- uses exact pupil detection from shruthi_neweyetrack.py
- outputs same format as mediapipe version
- generates 3d gaze vectors and angles
"""

import cv2
import numpy as np
import math
import time
from pupil_detector import detect_pupil_contour

class ContourGazeTracker:
    def __init__(self):
        self.frame_count = 0
        print("contour gaze tracker - press 'q' to quit")
        print("output: 3d gaze vectors and angles every 30 frames")


    def extract_gaze_numbers(self, pupil_center, roi_center, frame_shape):
        """extract 3d gaze vectors and angles - same format as mediapipe version"""
        
        if pupil_center is None:
            return None
        
        # get pupil and roi center coords
        pupil_x, pupil_y = pupil_center
        roi_x, roi_y = roi_center
        
        # calc exact roi center (middle of roi)
        h, w = frame_shape[:2]
        roi_width = int(w * 0.6)  # roi width
        roi_height = int(h * 0.5)  # roi height
        roi_center_x = int(w * 0.2) + roi_width // 2  # exact center of roi
        roi_center_y = int(h * 0.3) + roi_height // 2  # exact center of roi
        
        # calc deviation from roi center (in pixels)
        deviation_x = pupil_x - roi_center_x
        deviation_y = pupil_y - roi_center_y
        
        # normalize by roi dimensions - simple x-y plane
        offset_x = deviation_x / roi_width
        offset_y = -deviation_y / roi_height  # flip y so top = positive
        
        # convert to 3d gaze vectors (assuming 12mm eye radius)
        eye_radius = 12.0
        
        # single eye 3d vector
        x_3d = offset_x * eye_radius
        y_3d = offset_y * eye_radius
        z_3d = math.sqrt(max(0, eye_radius**2 - x_3d**2 - y_3d**2))
        gaze_vector = np.array([x_3d, y_3d, z_3d])
        gaze_vector = gaze_vector / np.linalg.norm(gaze_vector)
        
        # calc angles (in degrees)
        theta_h = math.degrees(math.atan2(gaze_vector[0], gaze_vector[2]))
        theta_v = math.degrees(math.atan2(gaze_vector[1], gaze_vector[2]))
        
        # single eye tracking - no fake left/right data
        return {
            'single_gaze_vector': gaze_vector.tolist(),
            'single_angles': [theta_h, theta_v],
            'single_offset': [offset_x, offset_y]
        }

    def run(self, camera_index=0):
        """main tracking loop"""
        # this is just here to try phone camera first fallback to local camera
        if isinstance(camera_index, str):
            cap = cv2.VideoCapture(camera_index)
        else:
            cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            print(f"[error] could not open camera {camera_index}")
            return
        
        # set camera properties
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        print("[info] starting contour gaze tracking...")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            self.frame_count += 1
            
            # detect pupil using contour analysis
            pupil_center, roi_center, bbox = detect_pupil_contour(frame)
            
            # extract gaze data
            if pupil_center is not None:
                gaze_data = self.extract_gaze_numbers(pupil_center, roi_center, frame.shape)
                
                # print every 30 frames
                if self.frame_count % 30 == 0:
                    print(f"\n=== Frame {self.frame_count} ===")
                    print(f"Single Eye Gaze Vector: {gaze_data['single_gaze_vector']}")
                    print(f"Single Eye Angles: H={gaze_data['single_angles'][0]:.1f}°, V={gaze_data['single_angles'][1]:.1f}°")
                    print(f"Single Eye Offset: {gaze_data['single_offset']}")
            
            # draw pupil detection
            if pupil_center:
                cv2.circle(frame, pupil_center, 5, (0, 255, 0), -1)
                
                # draw roi rectangle
                h, w = frame.shape[:2]
                roi_x1, roi_y1 = int(w*0.2), int(h*0.3)
                roi_x2, roi_y2 = int(w*0.8), int(h*0.8)
                cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 2)
            else:
                cv2.putText(frame, "NO PUPIL DETECTED", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # show frame
            cv2.imshow("Contour Gaze Tracker", frame)
            
            # exit on 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        print("[info] contour gaze tracking stopped")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='contour gaze tracker')
    parser.add_argument('--camera', type=int, default=0, help='camera index')
    args = parser.parse_args()
    
    tracker = ContourGazeTracker()
    tracker.run(camera_index=args.camera)

if __name__ == '__main__':
    main()
