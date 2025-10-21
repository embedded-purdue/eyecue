#!/usr/bin/env python3
"""
Standalone pupil detection module using contour analysis
- Extracted from contour_gaze_tracker.py for reuse across modules
"""

import cv2

def detect_pupil_contour(frame):
    """exact pupil detection from contour_gaze_tracker.py"""
    # convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # crop roi ~ single eye area (smaller, more focused)
    h, w = gray.shape
    roi = gray[int(h*0.4):int(h*0.7), int(w*0.35):int(w*0.65)]
    roi_color = frame[int(h*0.4):int(h*0.7), int(w*0.35):int(w*0.65)]
    
    # binarize -> pupil dark spot
    thresh = cv2.adaptiveThreshold(
        roi, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        21, 10
    )
    
    # find contours (blobs)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # assume biggest blob = pupil
        pupil = max(contours, key=cv2.contourArea)
        x, y, w_box, h_box = cv2.boundingRect(pupil)
        
        # calc center coords (relative to roi)
        cx = x + w_box // 2
        cy = y + h_box // 2
        
        # convert to full frame coords
        full_cx = cx + int(w*0.35)  # add roi offset
        full_cy = cy + int(h*0.4)  # add roi offset
        
        return (full_cx, full_cy), (cx, cy), (w_box, h_box)
    
    return None, None, None
