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
from io import BytesIO
from pupil_detector import detect_pupil_contour
from metrics_collector import MetricsCollector
from eyeball_model import EyeballModel

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
    def __init__(self, output_video=None, enable_metrics=True, metrics_save_interval=100):
        self.frame_count = 0
        self.esp32_capture = None
        self.is_local_camera = False
        # stabilization: smoothed pupil position
        self.smoothed_pupil_center = None
        self.smoothing_alpha = 0.3  # lower = more smoothing (0.0-1.0)
        # video recording
        self.output_video = output_video
        self.video_writer = None
        # metrics collection
        self.enable_metrics = enable_metrics
        self.metrics = MetricsCollector(save_interval=metrics_save_interval) if enable_metrics else None
        # eyeball sphere model – lazy-initialised on first frame so we know frame dimensions
        self.eyeball_model = None
        print("contour gaze tracker - press 'q' to quit")
        print("output: 3d gaze vectors and angles every 30 frames")
        if output_video:
            print(f"[info] recording video to: {output_video}")
        if enable_metrics:
            print(f"[info] metrics collection enabled (prints every {metrics_save_interval} frames)")


    def extract_gaze_numbers(self, pupil_center, frame_shape):
        """
        Extract 3-D gaze vectors and angles using a sphere-based eyeball model.

        Replaces the old linear pixel-offset approach with a proper pinhole
        camera ray → sphere intersection.

        The eyeball rotation centre is estimated adaptively each frame by
        intersecting the camera ray with the eye sphere (radius 12 mm) and
        nudging the center estimate with an exponential moving average.

        Returns the same dict keys as before so all callers work unchanged.
        Also includes 'eye_center_3d' and 'tilt_deg' for debugging.
        """
        if pupil_center is None:
            return None

        # Lazy-init: we need the frame dimensions to set up the camera model
        h, w = frame_shape[:2]
        if self.eyeball_model is None:
            self.eyeball_model = EyeballModel(frame_w=w, frame_h=h)
            print(f"[info] eyeball model initialised: f={self.eyeball_model.f:.0f}px, "
                  f"depth={self.eyeball_model.init_depth}mm")

        # Update the running eyeball-center estimate with this observation.
        # EyeballModel.update() is identical for the same (x,y) so duplicate
        # calls within one frame (metrics + display) do not double-update.
        self.eyeball_model.update(pupil_center)

        return self.eyeball_model.get_gaze_data(pupil_center)

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
            # detect pupil using contour analysis
            pupil_center, bbox = detect_pupil_contour(frame)
            detection_time = time.time() - detection_start if self.enable_metrics else None
            
            # stabilize pupil position using exponential moving average
            if pupil_center is not None:
                if self.smoothed_pupil_center is None:
                    # initialize with first detection
                    self.smoothed_pupil_center = pupil_center
                else:
                    # exponential smoothing: new = alpha * current + (1-alpha) * previous
                    self.smoothed_pupil_center = (
                        int(self.smoothing_alpha * pupil_center[0] + (1 - self.smoothing_alpha) * self.smoothed_pupil_center[0]),
                        int(self.smoothing_alpha * pupil_center[1] + (1 - self.smoothing_alpha) * self.smoothed_pupil_center[1])
                    )
                # use smoothed position for gaze calculation
                stable_pupil_center = self.smoothed_pupil_center
            else:
                # if detection fails, reset smoothed position after a few frames to avoid being stuck
                if self.frame_count % 10 == 0 and self.smoothed_pupil_center is not None:
                    # reset after 10 frames of failed detection
                    self.smoothed_pupil_center = None
                stable_pupil_center = self.smoothed_pupil_center if self.smoothed_pupil_center else None
            
            # record metrics
            if self.enable_metrics and self.metrics:
                gaze_angles = None
                if stable_pupil_center is not None:
                    gaze_data = self.extract_gaze_numbers(stable_pupil_center, frame.shape)
                    if gaze_data:
                        gaze_angles = tuple(gaze_data['single_angles'])
                self.metrics.record_frame(stable_pupil_center, detection_time, gaze_angles)
            
            # extract gaze data using stabilized position
            if stable_pupil_center is not None:
                gaze_data = self.extract_gaze_numbers(stable_pupil_center, frame.shape)
                
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
            roi_x1, roi_y1 = int(w*0.2), int(h*0.3)
            roi_x2, roi_y2 = int(w*0.8), int(h*0.8)
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
