#!/usr/bin/env python3
"""
Shruthi Vector Extractor - Terminal Output (every 30 frames)
"""

import cv2
import mediapipe as mp
import numpy as np
import math

# MediaPipe setup
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Eye landmark indices
LEFT_IRIS = [468, 469, 470, 471]
RIGHT_IRIS = [473, 474, 475, 476]
LEFT_CENTER = 468
RIGHT_CENTER = 473

def extract_gaze_numbers(landmarks, frame_shape):
    """Extract 3D gaze vectors and angles - returns numbers only"""
    
    # Get iris centers
    left_iris_x = sum([landmarks[i].x for i in LEFT_IRIS]) / len(LEFT_IRIS)
    left_iris_y = sum([landmarks[i].y for i in LEFT_IRIS]) / len(LEFT_IRIS)
    right_iris_x = sum([landmarks[i].x for i in RIGHT_IRIS]) / len(RIGHT_IRIS)
    right_iris_y = sum([landmarks[i].y for i in RIGHT_IRIS]) / len(RIGHT_IRIS)
    
    # Get eye centers
    left_eye_center = (landmarks[LEFT_CENTER].x, landmarks[LEFT_CENTER].y)
    right_eye_center = (landmarks[RIGHT_CENTER].x, landmarks[RIGHT_CENTER].y)
    
    # Calculate offsets (normalized coordinates)
    left_offset_x = left_iris_x - left_eye_center[0]
    left_offset_y = left_iris_y - left_eye_center[1]
    right_offset_x = right_iris_x - right_eye_center[0]
    right_offset_y = right_iris_y - right_eye_center[1]
    
    # Convert to 3D gaze vectors (assuming 12mm eye radius)
    eye_radius = 12.0
    
    # Left eye 3D vector
    left_x_3d = left_offset_x * eye_radius
    left_y_3d = left_offset_y * eye_radius
    left_z_3d = math.sqrt(max(0, eye_radius**2 - left_x_3d**2 - left_y_3d**2))
    left_gaze_vector = np.array([left_x_3d, left_y_3d, left_z_3d])
    left_gaze_vector = left_gaze_vector / np.linalg.norm(left_gaze_vector)
    
    # Right eye 3D vector
    right_x_3d = right_offset_x * eye_radius
    right_y_3d = right_offset_y * eye_radius
    right_z_3d = math.sqrt(max(0, eye_radius**2 - right_x_3d**2 - right_y_3d**2))
    right_gaze_vector = np.array([right_x_3d, right_y_3d, right_z_3d])
    right_gaze_vector = right_gaze_vector / np.linalg.norm(right_gaze_vector)
    
    # Calculate angles (in degrees)
    left_theta_h = math.degrees(math.atan2(left_gaze_vector[0], left_gaze_vector[2]))
    left_theta_v = math.degrees(math.atan2(left_gaze_vector[1], left_gaze_vector[2]))
    
    right_theta_h = math.degrees(math.atan2(right_gaze_vector[0], right_gaze_vector[2]))
    right_theta_v = math.degrees(math.atan2(right_gaze_vector[1], right_gaze_vector[2]))
    
    # Combined gaze
    combined_gaze = (left_gaze_vector + right_gaze_vector) / 2.0
    combined_gaze = combined_gaze / np.linalg.norm(combined_gaze)
    combined_theta_h = (left_theta_h + right_theta_h) / 2.0
    combined_theta_v = (left_theta_v + right_theta_v) / 2.0
    
    return {
        'left_gaze_vector': left_gaze_vector.tolist(),
        'right_gaze_vector': right_gaze_vector.tolist(),
        'combined_gaze_vector': combined_gaze.tolist(),
        'left_angles': [left_theta_h, left_theta_v],
        'right_angles': [right_theta_h, right_theta_v],
        'combined_angles': [combined_theta_h, combined_theta_v],
        'left_offset': [left_offset_x, left_offset_y],
        'right_offset': [right_offset_x, right_offset_y]
    }

# Main loop
cap = cv2.VideoCapture(0)
frame_count = 0

print("Simple Gaze Extractor - Press 'q' to quit")
print("Output: 3D gaze vectors and angles")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Convert to RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_frame)
    
    if results.multi_face_landmarks:
        landmarks = results.multi_face_landmarks[0].landmark
        gaze_data = extract_gaze_numbers(landmarks, frame.shape)

        # Get iris centers from the data we already calculated
        left_iris_x = sum([landmarks[i].x for i in LEFT_IRIS]) / len(LEFT_IRIS)
        left_iris_y = sum([landmarks[i].y for i in LEFT_IRIS]) / len(LEFT_IRIS)
        right_iris_x = sum([landmarks[i].x for i in RIGHT_IRIS]) / len(RIGHT_IRIS)
        right_iris_y = sum([landmarks[i].y for i in RIGHT_IRIS]) / len(RIGHT_IRIS)
        
        # Convert to pixel coordinates
        left_center_px = (int(left_iris_x * frame.shape[1]), int(left_iris_y * frame.shape[0]))
        right_center_px = (int(right_iris_x * frame.shape[1]), int(right_iris_y * frame.shape[0]))

        # Draw green dots
        cv2.circle(frame, left_center_px, 5, (0, 255, 0), -1)
        cv2.circle(frame, right_center_px, 5, (0, 255, 0), -1)
        
        # Print every 30 frames
        frame_count += 1
        if frame_count % 30 == 0:
            print(f"\n=== Frame {frame_count} ===")
            print(f"Combined Gaze Vector: {gaze_data['combined_gaze_vector']}")
            print(f"Combined Angles: H={gaze_data['combined_angles'][0]:.1f}°, V={gaze_data['combined_angles'][1]:.1f}°")
            print(f"Left Eye: H={gaze_data['left_angles'][0]:.1f}°, V={gaze_data['left_angles'][1]:.1f}°")
            print(f"Right Eye: H={gaze_data['right_angles'][0]:.1f}°, V={gaze_data['right_angles'][1]:.1f}°")
            print(f"Left Offset: {gaze_data['left_offset']}")
            print(f"Right Offset: {gaze_data['right_offset']}")
    
    # Simple display (just show the frame)
    cv2.imshow("Gaze Extractor", frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
