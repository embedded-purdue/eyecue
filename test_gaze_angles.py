#!/usr/bin/env python3
"""
test script to visualize gaze angles and screen position
"""

import cv2
import numpy as np
import math
import time
import pyautogui
from contour_gaze_tracker import ContourGazeTracker, ESP32CameraCapture
from pupil_detector import detect_pupil_contour

def angles_to_screen_coords_cursorcontroller(angle_h, angle_v, screen_width, screen_height, 
                                               screen_distance_pixels=None, 
                                               eye_center_h=0, eye_center_v=0,
                                               gyro_h=0, gyro_v=0, gyro_center_h=0, gyro_center_v=0):
    """
    convert gaze angles to screen coordinates using cursorcontroller's method.
    
    args:
        angle_h: horizontal eye angle in degrees
        angle_v: vertical eye angle in degrees
        screen_width: screen width in pixels
        screen_height: screen height in pixels
        screen_distance_pixels: distance from eyes to screen in pixels (auto-calculated if none)
        eye_center_h: horizontal calibration center angle in degrees (default: 0)
        eye_center_v: vertical calibration center angle in degrees (default: 0)
        gyro_h: current horizontal gyro angle in degrees (default: 0)
        gyro_v: current vertical gyro angle in degrees (default: 0)
        gyro_center_h: initial horizontal gyro angle in degrees (default: 0)
        gyro_center_v: initial vertical gyro angle in degrees (default: 0)
    
    returns:
        (screen_x, screen_y) tuple in pixels
    """
    # auto-calculate screen distance if not provided (using typical fov assumption)
    if screen_distance_pixels is None:
        # estimate based on screen width and typical viewing angle
        # assuming ~60 degree horizontal fov
        screen_distance_pixels = screen_width / (2 * math.tan(math.radians(30)))
    
    # convert angles to radians (matching cursorcontroller's update_target method)
    angle_h_rad = math.radians(angle_h)
    angle_v_rad = -math.radians(angle_v)  # negative: screen y increases downward
    
    # account for calibration (eye center)
    angle_h_rad -= math.radians(eye_center_h)
    angle_v_rad += math.radians(eye_center_v)
    
    # account for head rotation (gyro)
    angle_h_rad += math.radians(gyro_h - gyro_center_h)
    angle_v_rad += math.radians(gyro_v - gyro_center_v)
    
    # create gaze vector (matching cursorcontroller's method)
    unit_vector = np.array([
        math.sin(angle_h_rad) * math.cos(angle_v_rad),   # x-component
        math.cos(angle_h_rad) * math.cos(angle_v_rad),   # y-component
        math.sin(angle_v_rad)                             # z-component
    ])
    
    # scale unit vector according to distance from screen
    # avoid division by zero
    if abs(unit_vector[1]) < 1e-6:
        unit_vector[1] = 1e-6 if unit_vector[1] >= 0 else -1e-6
    
    scale_factor = screen_distance_pixels / unit_vector[1]
    
    # calculate position in screen coordinates
    x = (unit_vector[0] * scale_factor) + (screen_width / 2)
    y = (unit_vector[2] * scale_factor) + (screen_height / 2)
    
    # clamp to screen bounds
    x = max(0, min(screen_width - 1, x))
    y = max(0, min(screen_height - 1, y))
    
    return int(x), int(y)

def draw_screen_overlay(overlay_img, screen_width, screen_height, gaze_point):
    """draw screen representation with gaze point (no text)"""
    overlay_size = overlay_img.shape[1], overlay_img.shape[0]  # width, height
    
    # draw screen representation
    screen_scale_x = overlay_size[0] / screen_width
    screen_scale_y = overlay_size[1] / screen_height
    scale = min(screen_scale_x, screen_scale_y) * 0.9
    
    screen_w_scaled = int(screen_width * scale)
    screen_h_scaled = int(screen_height * scale)
    screen_x_offset = (overlay_size[0] - screen_w_scaled) // 2
    screen_y_offset = (overlay_size[1] - screen_h_scaled) // 2
    
    # draw screen border
    cv2.rectangle(overlay_img, 
                (screen_x_offset, screen_y_offset),
                (screen_x_offset + screen_w_scaled, screen_y_offset + screen_h_scaled),
                (100, 100, 100), 2)
    
    # draw center crosshair
    center_x = screen_x_offset + screen_w_scaled // 2
    center_y = screen_y_offset + screen_h_scaled // 2
    cv2.line(overlay_img, (center_x - 20, center_y), (center_x + 20, center_y), 
            (50, 50, 50), 1)
    cv2.line(overlay_img, (center_x, center_y - 20), (center_x, center_y + 20), 
            (50, 50, 50), 1)
    
    # draw gaze point if available
    if gaze_point:
        x, y = gaze_point
        # scale to overlay coordinates
        overlay_x = int(screen_x_offset + x * scale)
        overlay_y = int(screen_y_offset + y * scale)
        
        # draw large circle at gaze point
        radius = 25
        cv2.circle(overlay_img, (overlay_x, overlay_y), radius + 3, (0, 0, 255), 3)
        cv2.circle(overlay_img, (overlay_x, overlay_y), radius, (0, 255, 255), 2)
        cv2.circle(overlay_img, (overlay_x, overlay_y), 5, (0, 0, 255), -1)
        
        # draw crosshair
        crosshair_size = 30
        cv2.line(overlay_img, 
                (overlay_x - crosshair_size, overlay_y),
                (overlay_x + crosshair_size, overlay_y),
                (0, 0, 255), 2)
        cv2.line(overlay_img,
                (overlay_x, overlay_y - crosshair_size),
                (overlay_x, overlay_y + crosshair_size),
                (0, 0, 255), 2)

class GazeAngleTester:
    """test script that shows video, angles, and screen position"""
    def __init__(self, camera_index=0, screen_distance_mm=600):
        self.camera_index = camera_index
        self.screen_distance_mm = screen_distance_mm
        self.frame_count = 0
        self.esp32_capture = None
        self.is_local_camera = False
        self.smoothed_pupil_center = None
        self.smoothing_alpha = 0.3
        self.current_angles = None
        self.screen_width, self.screen_height = pyautogui.size()
        self.gaze_point = None
        self.overlay_window_created = False
        # use contour gaze tracker for gaze extraction
        self.gaze_tracker = ContourGazeTracker(enable_metrics=False)
        # convert screen distance from mm to pixels (~3.5 pixels per mm for typical monitor)
        pixels_per_mm = 3.5
        self.screen_distance_pixels = screen_distance_mm * pixels_per_mm
    
    def run(self):
        """main tracking loop with visualization"""
        # check if it's an esp32 camera stream
        is_esp32_stream = isinstance(self.camera_index, str) and self.camera_index.startswith('http://')
        
        if is_esp32_stream:
            print(f"[info] Connecting to ESP32 camera: {self.camera_index}")
            self.esp32_capture = ESP32CameraCapture(self.camera_index)
            cap = None
        else:
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                print(f"[error] Could not open camera/video: {self.camera_index}")
                return
            
            self.is_local_camera = isinstance(self.camera_index, int)
            if self.is_local_camera:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                print("[info] Local webcam detected - applying 8x zoom")
            else:
                print(f"[info] Processing video file: {self.camera_index}")
        
        print("[info] Starting gaze angle test visualization...")
        print("[info] This will show:")
        print("  1. Video with tracker overlays")
        print("  2. Gaze angles displayed on frame")
        print("  3. Screen overlay showing where you're looking")
        print(f"[info] Screen size: {self.screen_width}x{self.screen_height}")
        print("[info] Press 'q' to quit")
        
        # create overlay window in main thread
        overlay_size = (800, 600)
        overlay_img = np.zeros((overlay_size[1], overlay_size[0], 3), dtype=np.uint8)
        
        # create video window explicitly
        cv2.namedWindow("Gaze Tracker - Video Input", cv2.WINDOW_NORMAL)
        
        # get first frame
        if self.esp32_capture:
            ret, first_frame = self.esp32_capture.read()
        else:
            ret, first_frame = cap.read()
        
        if not ret:
            print("[error] Could not read first frame")
            return
        
        if first_frame is None:
            print("[error] First frame is None")
            return
        
        frame = first_frame
        print(f"[info] Frame size: {frame.shape}")
        
        while True:
            # flip frame horizontally (mirror effect)
            if frame is not None:
                frame = cv2.flip(frame, 1)  # 1 = horizontal flip
            
            # apply 8x zoom for local webcam
            if self.is_local_camera and frame is not None:
                h, w = frame.shape[:2]
                crop_w = w // 8
                crop_h = h // 8
                crop_x = (w - crop_w) // 2
                crop_y = (h - crop_h) // 2
                frame = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
            
            self.frame_count += 1
            
            # detect pupil
            pupil_center, roi_center, bbox = detect_pupil_contour(frame)
            
            # stabilize pupil position
            if pupil_center is not None:
                if self.smoothed_pupil_center is None:
                    self.smoothed_pupil_center = pupil_center
                else:
                    self.smoothed_pupil_center = (
                        int(self.smoothing_alpha * pupil_center[0] + (1 - self.smoothing_alpha) * self.smoothed_pupil_center[0]),
                        int(self.smoothing_alpha * pupil_center[1] + (1 - self.smoothing_alpha) * self.smoothed_pupil_center[1])
                    )
                stable_pupil_center = self.smoothed_pupil_center
            else:
                if self.frame_count % 10 == 0 and self.smoothed_pupil_center is not None:
                    self.smoothed_pupil_center = None
                stable_pupil_center = self.smoothed_pupil_center if self.smoothed_pupil_center else None
            
            # extract gaze data and output to terminal
            gaze_data = None
            if stable_pupil_center is not None:
                gaze_data = self.gaze_tracker.extract_gaze_numbers(stable_pupil_center, roi_center, frame.shape)
                if gaze_data:
                    self.current_angles = gaze_data['single_angles']
                    # calculate screen position using cursorcontroller's method
                    self.gaze_point = angles_to_screen_coords_cursorcontroller(
                        self.current_angles[0],  # angle_h in degrees
                        self.current_angles[1],  # angle_v in degrees
                        self.screen_width,
                        self.screen_height,
                        screen_distance_pixels=self.screen_distance_pixels
                    )
                    
                    # output to terminal
                    angle_h, angle_v = gaze_data['single_angles']
                    gaze_vector = gaze_data['single_gaze_vector']
                    offset = gaze_data['single_offset']
                    screen_x, screen_y = self.gaze_point
                    
                    print(f"Frame {self.frame_count:5d} | "
                          f"Gaze Vector: [{gaze_vector[0]:7.4f}, {gaze_vector[1]:7.4f}, {gaze_vector[2]:7.4f}] | "
                          f"Angles: H={angle_h:7.2f}°, V={angle_v:7.2f}° | "
                          f"Offset: [{offset[0]:6.3f}, {offset[1]:6.3f}] | "
                          f"Screen: ({screen_x}, {screen_y})")
            elif self.frame_count % 30 == 0:
                print(f"Frame {self.frame_count:5d} | NO PUPIL DETECTED")
            
            # draw on frame
            h, w = frame.shape[:2]
            
            # draw pupil detection
            if stable_pupil_center:
                cv2.circle(frame, stable_pupil_center, 5, (0, 255, 0), -1)
            if pupil_center:
                cv2.circle(frame, pupil_center, 3, (0, 0, 255), 2)
                if stable_pupil_center:
                    cv2.line(frame, pupil_center, stable_pupil_center, (255, 255, 0), 1)
            
            # draw roi rectangle
            roi_x1, roi_y1 = int(w*0.2), int(h*0.3)
            roi_x2, roi_y2 = int(w*0.8), int(h*0.8)
            cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 2)
            
            # show frame
            try:
                if frame is not None and frame.size > 0:
                    cv2.imshow("Gaze Tracker - Video Input", frame)
                else:
                    print(f"[warning] Invalid frame at frame {self.frame_count}")
            except Exception as e:
                print(f"[error] Error showing video frame: {e}")
            
            # update and show screen overlay
            try:
                overlay_img.fill(0)  # clear overlay
                draw_screen_overlay(overlay_img, self.screen_width, self.screen_height, self.gaze_point)
                
                if not self.overlay_window_created:
                    cv2.namedWindow("Screen Gaze Overlay", cv2.WINDOW_NORMAL)
                    cv2.resizeWindow("Screen Gaze Overlay", overlay_size[0], overlay_size[1])
                    self.overlay_window_created = True
                
                cv2.imshow("Screen Gaze Overlay", overlay_img)
            except Exception as e:
                print(f"[error] Error showing overlay: {e}")
            
            # exit on 'q'
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            
            # read next frame
            if self.esp32_capture:
                ret, frame = self.esp32_capture.read()
                if not ret:
                    print("[warning] Failed to get frame from ESP32, retrying...")
                    time.sleep(0.1)
                    continue
            else:
                ret, frame = cap.read()
                if not ret:
                    break
        
        # cleanup
        try:
            cv2.destroyWindow("Screen Gaze Overlay")
        except:
            pass
        if self.esp32_capture:
            self.esp32_capture.release()
        else:
            cap.release()
        cv2.destroyAllWindows()
        print("[info] Gaze angle test stopped")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Test gaze angles with visualization')
    parser.add_argument('--camera', type=str, default='0',
                       help='Camera index (int), video file path, or ESP32 stream URL')
    parser.add_argument('--distance', type=float, default=600,
                       help='Distance from eyes to screen in mm (default: 600)')
    args = parser.parse_args()
    
    # convert to int if it's a number
    try:
        camera_input = int(args.camera)
    except ValueError:
        camera_input = args.camera
    
    tester = GazeAngleTester(camera_index=camera_input, screen_distance_mm=args.distance)
    tester.run()

if __name__ == '__main__':
    main()

