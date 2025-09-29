#!/usr/bin/env python3
import cv2
import mediapipe as mp
import numpy as np
import time
import queue
from scipy.spatial.distance import euclidean

class BlinkDetector:
    def __init__(self):
        # MediaPipe setup 
        mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.65,
            min_tracking_confidence=0.70
        )

        # Eye landmarks 
        self.LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
        self.RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]
        self.LEFT_IRIS = [474, 475, 476, 477]
        self.RIGHT_IRIS = [469, 470, 471, 472]

        # blink detection parameters
        self.blink_threshold = 0.23   
        
        # Duration parameters
        self.min_blink_duration = 0.05  # 50ms minimum 
        self.max_blink_duration = 0.4   # 400ms maximum 
        
        # consecutive blink tracking 
        self.blink_queue = queue.Queue(maxsize=10)
        self.consec_blinks = []  
        
        # Blink state tracking 
        self.in_blink = False
        self.blink_start_time = 0.0
        self.last_pattern_time = 0.0
        self.pattern_cooldown = 0.9  # 0.9s cooldown

    def calculate_ear(self, eye_landmarks, landmarks):
        """Calculate Eye Aspect Ratio for given eye"""
        try:
            # Get eye landmark points
            points = np.array([[landmarks[i].x, landmarks[i].y] for i in eye_landmarks])
            
            # Calculate distances for EAR formula
            vertical_1 = euclidean(points[1], points[5])
            vertical_2 = euclidean(points[2], points[4])
            horizontal = euclidean(points[0], points[3])
            
            # EAR calculation
            ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
            return ear
        except:
            return 0.3  # Default if calculation fails

    def detect_blinks(self, landmarks, current_time):
        """Main blink detection logic"""
        # Calculate EAR for both eyes
        left_ear = self.calculate_ear(self.LEFT_EYE_IDX, landmarks)
        right_ear = self.calculate_ear(self.RIGHT_EYE_IDX, landmarks)
        avg_ear = (left_ear + right_ear) / 2.0

        # Check for blink start
        if avg_ear < self.blink_threshold:
            if not self.in_blink:
                self.in_blink = True
                self.blink_start_time = current_time
        
        # Check for blink end
        else:
            if self.in_blink:
                self.in_blink = False
                blink_duration = current_time - self.blink_start_time
                
                # Duration validation (0.06 < dur < 0.6)
                if 0.06 < blink_duration < 0.6:
                    # Consecutive blink tracking
                    self.consec_blinks.append(current_time)
                    self.consec_blinks = [tb for tb in self.consec_blinks if current_time - tb < 0.8]
                    
                    # Also maintain queue for additional validation
                    self.add_to_queue(current_time)
                    
                    # Check patterns using both methods
                    self.check_patterns(current_time)

    def add_to_queue(self, blink_time):
        """Add blink timestamp to FIFO queue (clean old entries)"""
        # Remove old blinks (>1 second ago)
        temp_blinks = []
        while not self.blink_queue.empty():
            old_time = self.blink_queue.get()
            if blink_time - old_time < 1.0:
                temp_blinks.append(old_time)
        
        # Add current blink and re-add recent ones
        temp_blinks.append(blink_time)
        temp_blinks.sort()  # Keep chronological order
        
        # Put back into queue
        for time in temp_blinks[-10:]:  # Keep only last 10 blinks
            if not self.blink_queue.full():
                self.blink_queue.put(time)

    def check_patterns(self, current_time):
        """Check for double/triple blink patterns using queue data"""
        # Cooldown check
        if current_time - self.last_pattern_time < self.pattern_cooldown:
            return
            
        # Get recent blinks from queue
        recent_blinks = list(self.blink_queue.queue)
        
        # Sort to ensure chronological order (safety check)
        recent_blinks.sort()
        
        # Check for triple blink first (3+ blinks within 1 second)
        if len(recent_blinks) >= 3:
            # Only check last 3 blinks for triple pattern
            last_three = recent_blinks[-3:]
            triple_time_window = current_time - last_three[0]
            
            if triple_time_window < 0.75:  # Research: triple blinks typically <750ms total
                self.check_triple_blink(recent_blinks, current_time)
            elif len(recent_blinks) >= 2:  # Fall back to double if triple is too slow
                self.check_double_blink(recent_blinks, current_time)
        
        # Check for double blink (2+ blinks)
        elif len(recent_blinks) >= 2:
            double_time_window = current_time - recent_blinks[-2]
            if double_time_window < 0.5:  # Research: double blinks typically <500ms total
                self.check_double_blink(recent_blinks, current_time)

    def check_triple_blink(self, recent_blinks, current_time):
        """Check for triple blink with research intervals"""
        # Check for 3+ consecutive blinks
        if len(self.consec_blinks) >= 3:
            # Cooldown pattern
            if current_time - self.last_pattern_time > 0.9:
                # Additional validation with queue data
                queue_blinks = list(self.blink_queue.queue)
                if len(queue_blinks) >= 3:
                    last_three = sorted(queue_blinks)[-3:]
                    
                    # Calculate intervals between blinks
                    interval_1 = last_three[1] - last_three[0]
                    interval_2 = last_three[2] - last_three[1]
                    total_duration = last_three[2] - last_three[0]
                    
                    # Research-based triple blink timing validation
                    if (0.10 < interval_1 < 0.30 and 
                        0.10 < interval_2 < 0.30 and 
                        total_duration < 0.75):
                        print("TRIPLE BLINK DETECTED")
                        self.clear_all_queues()
                        self.last_pattern_time = current_time
    
    def check_double_blink(self, recent_blinks, current_time):
        """Check for double blink with research intervals"""
        # Double blink logic: >= 2 consecutive blinks
        if len(self.consec_blinks) >= 2:
            # Cooldown: (t - self.last_pattern_time) > 0.9
            if current_time - self.last_pattern_time > 0.9:
                # Additional validation with queue data if available
                queue_blinks = list(self.blink_queue.queue)
                if len(queue_blinks) >= 2:
                    last_two = sorted(queue_blinks)[-2:]
                    interval = last_two[1] - last_two[0]
                    
                    # Research-based interval validation
                    if 0.10 < interval < 0.25:
                        print("DOUBLE BLINK DETECTED")
                        self.clear_all_queues()
                        self.last_pattern_time = current_time

    def clear_queue(self):
        """Empty the blink queue after pattern detection"""
        while not self.blink_queue.empty():
            self.blink_queue.get()
    
    def clear_all_queues(self):
        """Clear both queue and consecutive blinks"""
        self.clear_queue()
        self.consec_blinks = []  # Consecutive blinks list

def main():
    """Main camera loop"""
    # Camera setup
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera")
        return

    # Initialize detector
    detector = BlinkDetector()
    
    print("Double/Triple Blink Detector started")
    print("Looking for double and triple blink patterns...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Convert frame for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = detector.face_mesh.process(rgb_frame)
        current_time = time.time()
        
        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            
            # Run blink detection
            detector.detect_blinks(landmarks, current_time)
            
            # Draw green pupil tracker (from existing codebase)
            try:
                # Left iris center
                left_iris_x = sum([landmarks[i].x for i in detector.LEFT_IRIS]) / len(detector.LEFT_IRIS)
                left_iris_y = sum([landmarks[i].y for i in detector.LEFT_IRIS]) / len(detector.LEFT_IRIS)
                left_center = (int(left_iris_x * frame.shape[1]), int(left_iris_y * frame.shape[0]))
                
                # Right iris center
                right_iris_x = sum([landmarks[i].x for i in detector.RIGHT_IRIS]) / len(detector.RIGHT_IRIS)
                right_iris_y = sum([landmarks[i].y for i in detector.RIGHT_IRIS]) / len(detector.RIGHT_IRIS)
                right_center = (int(right_iris_x * frame.shape[1]), int(right_iris_y * frame.shape[0]))
                
                # Draw green dots
                cv2.circle(frame, left_center, 5, (0, 255, 0), -1)
                cv2.circle(frame, right_center, 5, (0, 255, 0), -1)
            except:
                pass
        
        # Show frame
        cv2.imshow("Blink Detector", frame)
        
        # Exit on 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    print("Blink detector stopped.")

if __name__ == "__main__":
    main()
