#!/usr/bin/env python3
"""
metrics collector for pupil detection and gaze tracking
tracks detection rate, fps, latency, position stability, accuracy
"""

import time
import json
import csv
import numpy as np
from collections import deque
from datetime import datetime
from typing import Optional, Tuple, List, Dict


class MetricsCollector:
    """collects and analyzes metrics for pupil detection and gaze tracking"""
    
    def __init__(self, window_size: int = 30, save_interval: int = 100):
        """
        Args:
            window_size: number of recent frames for rolling averages
            save_interval: save metrics to file every n frames
        """
        self.window_size = window_size
        self.save_interval = save_interval
        
        # detection metrics
        self.total_frames = 0
        self.successful_detections = 0
        self.detection_history = deque(maxlen=window_size)  # true/false per frame
        
        # performance metrics
        self.frame_times = deque(maxlen=window_size)  # time between frames
        self.detection_times = deque(maxlen=window_size)  # time to detect pupil
        self.last_frame_time = None
        
        # position stability metrics
        self.pupil_positions = deque(maxlen=window_size)
        self.position_deltas = deque(maxlen=window_size-1)  # distance between consecutive detections
        
        # accuracy metrics (if ground truth provided)
        self.ground_truth_positions = []
        self.predicted_positions = []
        self.error_distances = []
        
        # gaze angle metrics
        self.gaze_angles = deque(maxlen=window_size)
        self.gaze_angle_changes = deque(maxlen=window_size-1)
        
        # statistics
        self.start_time = time.time()
        self.last_save_time = time.time()
        
    def record_frame(self, pupil_center: Optional[Tuple[int, int]], 
                     detection_time: Optional[float] = None,
                     gaze_angles: Optional[Tuple[float, float]] = None):
        """record a frame's detection result"""
        current_time = time.time()
        self.total_frames += 1
        
        # detection metrics
        detected = pupil_center is not None
        self.detection_history.append(detected)
        if detected:
            self.successful_detections += 1
        
        # performance metrics
        if self.last_frame_time is not None:
            frame_time = current_time - self.last_frame_time
            self.frame_times.append(frame_time)
        
        if detection_time is not None:
            self.detection_times.append(detection_time)
        
        self.last_frame_time = current_time
        
        # position stability
        if pupil_center is not None:
            self.pupil_positions.append(pupil_center)
            
            # calculate position delta from previous frame
            if len(self.pupil_positions) >= 2:
                prev_pos = self.pupil_positions[-2]
                curr_pos = self.pupil_positions[-1]
                delta = np.sqrt((curr_pos[0] - prev_pos[0])**2 + 
                               (curr_pos[1] - prev_pos[1])**2)
                self.position_deltas.append(delta)
        
        # gaze angle metrics
        if gaze_angles is not None:
            self.gaze_angles.append(gaze_angles)
            if len(self.gaze_angles) >= 2:
                prev_angles = self.gaze_angles[-2]
                curr_angles = self.gaze_angles[-1]
                angle_change = np.sqrt((curr_angles[0] - prev_angles[0])**2 +
                                      (curr_angles[1] - prev_angles[1])**2)
                self.gaze_angle_changes.append(angle_change)
    
    def record_ground_truth(self, predicted_pos: Tuple[int, int], 
                           ground_truth_pos: Tuple[int, int]):
        """record predicted vs ground truth for accuracy calculation"""
        self.predicted_positions.append(predicted_pos)
        self.ground_truth_positions.append(ground_truth_pos)
        
        error = np.sqrt((predicted_pos[0] - ground_truth_pos[0])**2 +
                       (predicted_pos[1] - ground_truth_pos[1])**2)
        self.error_distances.append(error)
    
    def get_detection_rate(self) -> float:
        """get overall detection rate (0.0 to 1.0)"""
        if self.total_frames == 0:
            return 0.0
        return self.successful_detections / self.total_frames
    
    def get_recent_detection_rate(self) -> float:
        """get detection rate over recent window"""
        if len(self.detection_history) == 0:
            return 0.0
        return sum(self.detection_history) / len(self.detection_history)
    
    def get_fps(self) -> float:
        """get current fps (frames per second)"""
        if len(self.frame_times) == 0:
            return 0.0
        avg_frame_time = np.mean(self.frame_times)
        return 1.0 / avg_frame_time if avg_frame_time > 0 else 0.0
    
    def get_avg_detection_time(self) -> float:
        """get average time to detect pupil (milliseconds)"""
        if len(self.detection_times) == 0:
            return 0.0
        return np.mean(self.detection_times) * 1000  # convert to ms
    
    def get_position_jitter(self) -> float:
        """get position jitter (standard deviation of position deltas) in pixels"""
        if len(self.position_deltas) < 2:
            return 0.0
        return np.std(self.position_deltas)
    
    def get_position_variance(self) -> Tuple[float, float]:
        """get variance in x and y positions separately"""
        if len(self.pupil_positions) < 2:
            return (0.0, 0.0)
        positions = np.array(self.pupil_positions)
        return (float(np.var(positions[:, 0])), float(np.var(positions[:, 1])))
    
    def get_accuracy_stats(self) -> Dict[str, float]:
        """get accuracy statistics if ground truth is available"""
        if len(self.error_distances) == 0:
            return {}
        
        errors = np.array(self.error_distances)
        return {
            'mean_error_px': float(np.mean(errors)),
            'median_error_px': float(np.median(errors)),
            'std_error_px': float(np.std(errors)),
            'max_error_px': float(np.max(errors)),
            'min_error_px': float(np.min(errors)),
            'rmse_px': float(np.sqrt(np.mean(errors**2)))
        }
    
    def get_gaze_stability(self) -> float:
        """get gaze angle change rate (degrees per frame)"""
        if len(self.gaze_angle_changes) == 0:
            return 0.0
        return np.mean(self.gaze_angle_changes)
    
    def get_summary(self) -> Dict:
        """get comprehensive summary of all metrics"""
        runtime = time.time() - self.start_time
        
        summary = {
            'runtime_seconds': runtime,
            'total_frames': self.total_frames,
            'detection_rate': self.get_detection_rate(),
            'recent_detection_rate': self.get_recent_detection_rate(),
            'fps': self.get_fps(),
            'avg_detection_time_ms': self.get_avg_detection_time(),
            'position_jitter_px': self.get_position_jitter(),
            'position_variance': self.get_position_variance(),
        }
        
        # add accuracy stats if available
        accuracy_stats = self.get_accuracy_stats()
        if accuracy_stats:
            summary['accuracy'] = accuracy_stats
        
        # add gaze stability if available
        if len(self.gaze_angles) > 0:
            summary['gaze_stability_deg_per_frame'] = self.get_gaze_stability()
        
        return summary
    
    def print_summary(self, prefix: str = ""):
        """print formatted summary to console"""
        summary = self.get_summary()
        print(f"\n{prefix}=== Metrics Summary ===")
        print(f"{prefix}Runtime: {summary['runtime_seconds']:.1f}s")
        print(f"{prefix}Total Frames: {summary['total_frames']}")
        print(f"{prefix}Detection Rate: {summary['detection_rate']:.1%} ({summary['recent_detection_rate']:.1%} recent)")
        print(f"{prefix}FPS: {summary['fps']:.1f}")
        print(f"{prefix}Avg Detection Time: {summary['avg_detection_time_ms']:.2f}ms")
        print(f"{prefix}Position Jitter: {summary['position_jitter_px']:.2f}px")
        print(f"{prefix}Position Variance: X={summary['position_variance'][0]:.2f}, Y={summary['position_variance'][1]:.2f}")
        
        if 'accuracy' in summary:
            acc = summary['accuracy']
            print(f"{prefix}Accuracy:")
            print(f"{prefix}  Mean Error: {acc['mean_error_px']:.2f}px")
            print(f"{prefix}  RMSE: {acc['rmse_px']:.2f}px")
            print(f"{prefix}  Max Error: {acc['max_error_px']:.2f}px")
        
        if 'gaze_stability_deg_per_frame' in summary:
            print(f"{prefix}Gaze Stability: {summary['gaze_stability_deg_per_frame']:.3f} deg/frame")
        print()
    
    def save_to_json(self, filename: Optional[str] = None):
        """save metrics to json file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"metrics_{timestamp}.json"
        
        summary = self.get_summary()
        
        # add detailed position history if available
        if len(self.pupil_positions) > 0:
            summary['recent_positions'] = list(self.pupil_positions)
        
        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"[METRICS] Saved to {filename}")
        return filename
    
    def save_to_csv(self, filename: Optional[str] = None):
        """save frame-by-frame metrics to csv"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"metrics_frame_{timestamp}.csv"
        
        # save summary (no frame-by-frame storage)
        summary = self.get_summary()
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Metric', 'Value'])
            for key, value in summary.items():
                if isinstance(value, (list, tuple)):
                    writer.writerow([key, ','.join(map(str, value))])
                else:
                    writer.writerow([key, value])
        
        print(f"[METRICS] Saved CSV to {filename}")
        return filename
    
    def reset(self):
        """reset all metrics"""
        self.total_frames = 0
        self.successful_detections = 0
        self.detection_history.clear()
        self.frame_times.clear()
        self.detection_times.clear()
        self.pupil_positions.clear()
        self.position_deltas.clear()
        self.ground_truth_positions.clear()
        self.predicted_positions.clear()
        self.error_distances.clear()
        self.gaze_angles.clear()
        self.gaze_angle_changes.clear()
        self.last_frame_time = None
        self.start_time = time.time()


