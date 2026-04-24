#!/usr/bin/env python3
"""
contour-based gaze tracker
uses exact pupil detection, outputs same format as mediapipe version
generates 3d gaze vectors and angles
"""

import cv2
import numpy as np
import math
import time
import requests
from typing import Optional, Tuple, Sequence, Union, Dict
from pupil_detector import detect_pupil_contour, PupilTracker, OneEuroFilter2D
from metrics_collector import MetricsCollector


def extract_contour_gaze_data(
    pupil_center: Optional[Sequence[Union[int, float]]],
    frame_shape: Sequence[int],
) -> Optional[Dict[str, list]]:
    """Convert pupil center to contour gaze vector/angles."""
    if pupil_center is None:
        return None

    if not frame_shape or len(frame_shape) < 2:
        return None

    pupil_x, pupil_y = pupil_center
    h = int(frame_shape[0])
    w = int(frame_shape[1])
    if h <= 0 or w <= 0:
        return None

    roi_width = int(w * 0.5)
    roi_height = int(h * 0.45)
    if roi_width <= 0 or roi_height <= 0:
        return None

    roi_center_x = int(w * 0.25) + roi_width // 2
    roi_center_y = int(h * 0.3) + roi_height // 2

    deviation_x = float(pupil_x) - roi_center_x
    deviation_y = float(pupil_y) - roi_center_y

    offset_x = deviation_x / roi_width
    offset_y = -deviation_y / roi_height

    eye_radius = 12.0
    x_3d = offset_x * eye_radius
    y_3d = offset_y * eye_radius
    z_3d = math.sqrt(max(0.0, eye_radius**2 - x_3d**2 - y_3d**2))
    gaze_vector = np.array([x_3d, y_3d, z_3d], dtype=np.float64)
    gaze_norm = np.linalg.norm(gaze_vector)
    if gaze_norm <= 0:
        return None
    gaze_vector = gaze_vector / gaze_norm

    theta_h = math.degrees(math.atan2(gaze_vector[0], gaze_vector[2]))
    theta_v = math.degrees(math.atan2(gaze_vector[1], gaze_vector[2]))

    return {
        "single_gaze_vector": gaze_vector.tolist(),
        "single_angles": [theta_h, theta_v],
        "single_offset": [offset_x, offset_y],
    }


def map_gaze_angles_to_screen(
    angle_h: float,
    angle_v: float,
    screen_width: int,
    screen_height: int,
    *,
    screen_distance_pixels: Optional[float] = None,
    eye_center_h: float = 0.0,
    eye_center_v: float = 0.0,
    gyro_h: float = 0.0,
    gyro_v: float = 0.0,
    gyro_center_h: float = 0.0,
    gyro_center_v: float = 0.0,
) -> Tuple[int, int]:
    """Map gaze angles to screen coordinates using CursorController geometry."""
    width = max(1, int(screen_width))
    height = max(1, int(screen_height))

    if screen_distance_pixels is None:
        # FOV governs sensitivity: larger FOV = more amplification.
        # 55° gives ~2.5× more sensitivity than the old 30° value,
        # letting small pupil movements cover the full screen.
        screen_distance_pixels = width / (2 * math.tan(math.radians(55)))

    angle_h_rad = math.radians(float(angle_h))
    angle_v_rad = -math.radians(float(angle_v))

    angle_h_rad -= math.radians(float(eye_center_h))
    angle_v_rad += math.radians(float(eye_center_v))

    angle_h_rad += math.radians(float(gyro_h) - float(gyro_center_h))
    angle_v_rad += math.radians(float(gyro_v) - float(gyro_center_v))

    unit_vector = np.array(
        [
            math.sin(angle_h_rad) * math.cos(angle_v_rad),
            math.cos(angle_h_rad) * math.cos(angle_v_rad),
            math.sin(angle_v_rad),
        ],
        dtype=np.float64,
    )

    if abs(unit_vector[1]) < 1e-6:
        unit_vector[1] = 1e-6 if unit_vector[1] >= 0 else -1e-6

    scale_factor = float(screen_distance_pixels) / unit_vector[1]

    x = (unit_vector[0] * scale_factor) + (width / 2)
    y = (unit_vector[2] * scale_factor) + (height / 2)

    x = max(0, min(width - 1, x))
    y = max(0, min(height - 1, y))
    return int(x), int(y)


class ESP32CameraCapture:
    """helper class to capture frames from esp32 camera"""
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.capture_url = f"{self.base_url}/capture"
        self.stream_url = f"{self.base_url}/stream"
        # try stream first, fall back to capture
        self.use_stream = True
        self.cap = None
        self._init_capture()
    
    def _init_capture(self):
        """initialize capture method"""
        # extract ip from base_url
        if '://' in self.base_url:
            ip = self.base_url.split('://')[-1].split('/')[0].split(':')[0]
        else:
            ip = self.base_url.split('/')[0].split(':')[0]
        
        # try stream endpoint on port 81 first (esp32 stream server)
        stream_url_81 = f"http://{ip}:81/stream"
        try:
            self.cap = cv2.VideoCapture(stream_url_81)
            if self.cap.isOpened():
                ret, _ = self.cap.read()
                if ret:
                    print(f"[info] using stream endpoint: {stream_url_81}")
                    self.stream_url = stream_url_81
                    return
                self.cap.release()
        except:
            pass
        
        # try stream endpoint on port 80 (default)
        try:
            self.cap = cv2.VideoCapture(self.stream_url)
            if self.cap.isOpened():
                ret, _ = self.cap.read()
                if ret:
                    print(f"[info] using stream endpoint: {self.stream_url}")
                    return
                self.cap.release()
        except:
            pass
        
        # fall back to capture endpoint (single frame requests)
        self.use_stream = False
        self.cap = None
        print(f"[info] stream not available, using capture endpoint: {self.capture_url}")
    
    def read(self):
        """read a frame from esp32 camera"""
        if self.use_stream and self.cap:
            return self.cap.read()
        else:
            # use capture endpoint
            try:
                response = requests.get(self.capture_url, timeout=2)
                if response.status_code == 200:
                    img_array = np.frombuffer(response.content, np.uint8)
                    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if frame is not None:
                        return True, frame
            except Exception as e:
                print(f"[warning] capture error: {e}")
            return False, None
    
    def release(self):
        """release resources"""
        if self.cap:
            self.cap.release()
            self.cap = None

class ContourGazeTracker:
    def __init__(self, output_video=None, enable_metrics=True, metrics_save_interval=100, quiet=False):
        self.frame_count = 0
        self.esp32_capture = None
        self.is_local_camera = False
        self.quiet = bool(quiet)
        # stateful pupil tracker (windowed search + jump rejection + ellipse fit)
        self.pupil_tracker = PupilTracker()
        # adaptive 1€ smoothing (kills fixation jitter, stays responsive on saccades)
        self.smoother = OneEuroFilter2D()
        self.smoothed_pupil_center = None
        # confidence floor for downstream gaze use
        self.confidence_floor = 0.30
        # video recording
        self.output_video = output_video
        self.video_writer = None
        # metrics collection
        self.enable_metrics = enable_metrics
        self.metrics = MetricsCollector(save_interval=metrics_save_interval) if enable_metrics else None
        if not self.quiet:
            print("contour gaze tracker - press 'q' to quit")
            print("output: 3d gaze vectors and angles every 30 frames")
            if output_video:
                print(f"[info] recording video to: {output_video}")
            if enable_metrics:
                print(f"[info] metrics collection enabled (prints every {metrics_save_interval} frames)")


    def extract_gaze_numbers(self, pupil_center, roi_center, frame_shape):
        """extract 3d gaze vectors and angles - same format as mediapipe version"""
        
        if pupil_center is None:
            return None
        
        # get pupil coords
        pupil_x, pupil_y = pupil_center
        
        # calc exact roi center (middle of roi) - roi_center parameter is not used
        h, w = frame_shape[:2]
        roi_width = int(w * 0.5)  # roi width (matches pupil_detector: 0.25 to 0.75)
        roi_height = int(h * 0.45)  # roi height (matches pupil_detector: 0.3 to 0.75)
        roi_center_x = int(w * 0.25) + roi_width // 2  # exact center of roi
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
        
        # check if it's an esp32 camera stream url
        is_esp32_stream = isinstance(camera_index, str) and camera_index.startswith('http://')
        
        if is_esp32_stream:
            # use esp32-specific capture
            print(f"[info] connecting to ESP32 camera: {camera_index}")
            self.esp32_capture = ESP32CameraCapture(camera_index)
            cap = None  # we'll use esp32_capture.read() instead
        else:
            cap = cv2.VideoCapture(camera_index)
            if not cap.isOpened():
                print(f"[error] could not open camera/video: {camera_index}")
                return
            
            # set camera properties only if it's a local camera (integer), not a video file
            self.is_local_camera = isinstance(camera_index, int)
            if self.is_local_camera:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                print("[info] local webcam detected - applying 8x zoom")
            else:
                print(f"[info] processing video file: {camera_index}")
        
        print("[info] starting contour gaze tracking...")
        
        # get first frame to determine video dimensions
        if self.esp32_capture:
            ret, first_frame = self.esp32_capture.read()
        else:
            ret, first_frame = cap.read()
        
        if not ret:
            print("[error] could not read first frame")
            return
        
        # initialize video writer if output file specified
        if self.output_video and first_frame is not None:
            h, w = first_frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = 30.0  # default fps
            if cap:
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.video_writer = cv2.VideoWriter(self.output_video, fourcc, fps, (w, h))
            if not self.video_writer.isOpened():
                print(f"[error] could not open video writer for: {self.output_video}")
                self.video_writer = None
            else:
                print(f"[info] video recording initialized: {w}x{h} @ {fps}fps")
        
        # process first frame
        frame = first_frame
        
        while True:
            # apply 8x zoom for local webcam
            if self.is_local_camera and frame is not None:
                h, w = frame.shape[:2]
                # crop center 1/8 of the frame (zoom in 8x)
                crop_w = w // 8
                crop_h = h // 8
                crop_x = (w - crop_w) // 2
                crop_y = (h - crop_h) // 2
                frame = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
                # resize back to original size
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
            
            self.frame_count += 1
            
            # time detection for metrics
            detection_start = time.time()
            track = self.pupil_tracker.update(frame)
            detection_time = time.time() - detection_start if self.enable_metrics else None

            pupil_center = track['center']
            confidence = track['confidence']
            bbox = track['bbox']
            roi_center = None  # unused downstream; kept for signature parity

            if pupil_center is not None and confidence >= self.confidence_floor:
                sx, sy = self.smoother(pupil_center)
                self.smoothed_pupil_center = (int(round(sx)), int(round(sy)))
                stable_pupil_center = self.smoothed_pupil_center
            elif pupil_center is not None and self.smoothed_pupil_center is not None:
                # low-confidence frame: hold last smoothed position
                stable_pupil_center = self.smoothed_pupil_center
            else:
                # full miss: reset smoother so we don't snap on re-acquire
                self.smoother.reset()
                self.smoothed_pupil_center = None
                stable_pupil_center = None
            
            # record metrics
            if self.enable_metrics and self.metrics:
                gaze_angles = None
                if stable_pupil_center is not None:
                    gaze_data = self.extract_gaze_numbers(stable_pupil_center, roi_center, frame.shape)
                    if gaze_data:
                        gaze_angles = tuple(gaze_data['single_angles'])
                self.metrics.record_frame(stable_pupil_center, detection_time, gaze_angles)
            
            # extract gaze data using stabilized position
            if stable_pupil_center is not None:
                gaze_data = self.extract_gaze_numbers(stable_pupil_center, roi_center, frame.shape)
                
                # print every 30 frames
                if self.frame_count % 30 == 0:
                    print(f"\n=== Frame {self.frame_count} ===")
                    print(f"Single Eye Gaze Vector: {gaze_data['single_gaze_vector']}")
                    print(f"Single Eye Angles: H={gaze_data['single_angles'][0]:.1f}°, V={gaze_data['single_angles'][1]:.1f}°")
                    print(f"Single Eye Offset: {gaze_data['single_offset']}")
                    
                    # print metrics summary every 30 frames
                    if self.enable_metrics and self.metrics:
                        print(f"Detection Rate: {self.metrics.get_recent_detection_rate():.1%} | "
                              f"FPS: {self.metrics.get_fps():.1f} | "
                              f"Jitter: {self.metrics.get_position_jitter():.2f}px")
            
            # draw pupil detection (use stabilized position)
            if stable_pupil_center:
                # draw smoothed position in green
                cv2.circle(frame, stable_pupil_center, 5, (0, 255, 0), -1)
            # always draw raw detection if available (for debugging)
            if pupil_center:
                cv2.circle(frame, pupil_center, 3, (0, 0, 255), 2)
                # draw line connecting raw to smoothed if both exist
                if stable_pupil_center:
                    cv2.line(frame, pupil_center, stable_pupil_center, (255, 255, 0), 1)
            
            # draw roi rectangle (always visible)
            h, w = frame.shape[:2]
            roi_x1, roi_y1 = int(w*0.25), int(h*0.3)
            roi_x2, roi_y2 = int(w*0.75), int(h*0.75)
            cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 2)
            
            # display metrics on frame
            if self.enable_metrics and self.metrics:
                metrics_text = [
                    f"FPS: {self.metrics.get_fps():.1f}",
                    f"Detection: {self.metrics.get_recent_detection_rate():.1%}",
                    f"Jitter: {self.metrics.get_position_jitter():.1f}px"
                ]
                y_offset = 30
                for i, text in enumerate(metrics_text):
                    cv2.putText(frame, text, (10, y_offset + i*25), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            
            if not stable_pupil_center and not pupil_center:
                cv2.putText(frame, "NO PUPIL DETECTED", (10, h - 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # write frame to video if recording
            if self.video_writer:
                self.video_writer.write(frame)
            
            # show frame
            cv2.imshow("Contour Gaze Tracker", frame)
            
            # exit on 'q', save metrics on 's'
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s') and self.enable_metrics and self.metrics:
                self.metrics.save_to_json()
                self.metrics.save_to_csv()
            
            # read next frame
            if self.esp32_capture:
                ret, frame = self.esp32_capture.read()
            else:
                ret, frame = cap.read()
            
            if not ret:
                if self.esp32_capture:
                    print("[warning] failed to get frame from ESP32, retrying...")
                    time.sleep(0.1)
                    continue
                break
        
        # release video writer
        if self.video_writer:
            self.video_writer.release()
            print(f"[info] video saved to: {self.output_video}")
        
        if self.esp32_capture:
            self.esp32_capture.release()
        else:
            cap.release()
        cv2.destroyAllWindows()
        
        # print and save final metrics
        if self.enable_metrics and self.metrics:
            print("\n[info] Final metrics summary:")
            self.metrics.print_summary()
            self.metrics.save_to_json()
            self.metrics.save_to_csv()
        
        print("[info] contour gaze tracking stopped")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='contour gaze tracker')
    parser.add_argument('--camera', type=str, default='0', 
                       help='camera index (int), video file path (str), or ESP32 stream URL (e.g., http://192.168.4.49/stream)')
    parser.add_argument('--output', type=str, default=None,
                       help='output video file path (e.g., output.mp4)')
    parser.add_argument('--no-metrics', action='store_true',
                       help='disable metrics collection')
    parser.add_argument('--metrics-interval', type=int, default=100,
                       help='interval for auto-saving metrics (frames)')
    args = parser.parse_args()
    
    # convert to int if it's a number, otherwise keep as string (video file path or url)
    try:
        camera_input = int(args.camera)
    except ValueError:
        camera_input = args.camera
    
    tracker = ContourGazeTracker(
        output_video=args.output,
        enable_metrics=not args.no_metrics,
        metrics_save_interval=args.metrics_interval
    )
    tracker.run(camera_index=camera_input)

if __name__ == '__main__':
    main()
