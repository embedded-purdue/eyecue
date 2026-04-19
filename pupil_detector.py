#!/usr/bin/env python3
"""
standalone pupil detection module using contour analysis
- extracted from contour_gaze_tracker.py for reuse across modules
"""

import cv2
import numpy as np

def detect_pupil_contour(frame):
    """pupil detection using darkest region with size filtering"""

    # DEBUG: Check frame validity
    if frame is None:
        print("[DEBUG] Frame is None!")
        return None, None, None

    print(f"[DEBUG] Frame shape: {frame.shape}, dtype: {frame.dtype}, min: {frame.min()}, max: {frame.max()}")

    # convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    print(f"[DEBUG] Gray shape: {gray.shape}, min: {gray.min()}, max: {gray.max()}")
    
    # crop roi ~ single eye area (smaller, more focused)
    h, w = gray.shape
    roi = gray[int(h*0.4):int(h*0.7), int(w*0.35):int(w*0.65)]
    print(f"[DEBUG] ROI shape: {roi.shape}")

    # apply slight blur to reduce noise
    blurred = cv2.GaussianBlur(roi, (3, 3), 0)

    # use adaptive threshold based on image brightness
    # For bright images (like overexposed streams), use a more aggressive threshold
    mean_intensity = np.mean(blurred)
    min_intensity = np.min(blurred)

    # If the darkest pixel is still quite bright (>80), the image is overexposed
    # Use a higher threshold percentage to still capture the relatively darker regions
    if min_intensity > 80:
        # Overexposed - use 65% of mean to capture the pupil
        threshold_value = mean_intensity * 0.65
        print(f"[DEBUG] OVEREXPOSED image detected (min={min_intensity})")
    else:
        # Normal exposure - use conservative threshold
        threshold_value = max(30, mean_intensity * 0.4)

    print(f"[DEBUG] Mean intensity: {mean_intensity:.1f}, Min: {min_intensity}, Threshold: {threshold_value:.1f}")
    _, thresh = cv2.threshold(blurred, threshold_value, 255, cv2.THRESH_BINARY_INV)
    
    # morphological operations to clean up - remove small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"[DEBUG] Found {len(contours)} contours")

    if not contours:
        print("[DEBUG] No contours found - returning None")
        return None, None, None
    
    roi_h, roi_w = roi.shape
    roi_area = roi_h * roi_w
    
    # filter and score contours
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        
        # size filter: pupil should be reasonably sized (not too small, not iris-sized)
        if area < 20 or area > roi_area * 0.25:  # 20-25% of roi max
            continue
        
        # get bounding box for aspect ratio check
        x, y, w_box, h_box = cv2.boundingRect(contour)
        aspect_ratio = float(w_box) / h_box if h_box > 0 else 0
        
        # pupil should be roughly round (not elongated like eyelashes)
        if aspect_ratio < 0.5 or aspect_ratio > 2.0:
            continue
        
        # get mean intensity of this region (pupil should be very dark)
        mask = np.zeros(roi.shape, dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        mean_intensity = cv2.mean(blurred, mask=mask)[0]
        
        # calculate circularity
        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        
        # prefer darker, more circular, reasonably sized blobs
        # weight darkness more heavily
        score = (255 - mean_intensity) * 0.7 + circularity * 50 * 0.3
        
        candidates.append({
            'contour': contour,
            'score': score,
            'mean_intensity': mean_intensity,
            'area': area
        })
    
    print(f"[DEBUG] After filtering: {len(candidates)} valid candidates")

    if not candidates:
        print("[DEBUG] No valid candidates after filtering - returning None")
        return None, None, None

    # sort by score and take the best one
    candidates.sort(key=lambda x: x['score'], reverse=True)
    best = candidates[0]
    print(f"[DEBUG] Best candidate - score: {best['score']:.1f}, area: {best['area']:.0f}, intensity: {best['mean_intensity']:.1f}")
    
    # use moments for accurate center
    M = cv2.moments(best['contour'])
    if M["m00"] != 0:
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
    else:
        x, y, w_box, h_box = cv2.boundingRect(best['contour'])
        cx = x + w_box // 2
        cy = y + h_box // 2
    
    # get bounding box
    x, y, w_box, h_box = cv2.boundingRect(best['contour'])
    
    # convert to full frame coords
    full_cx = cx + int(w*0.35)
    full_cy = cy + int(h*0.4)

    print(f"[DEBUG] SUCCESS - Pupil detected at ({full_cx}, {full_cy})")
    print("-" * 60)

    return (full_cx, full_cy), (cx, cy), (w_box, h_box)


def detect_pupil_contour_candidates(frame):
    """
    pupil detection that returns ALL scored candidates (sorted best-to-worst)
    plus the roi offset so callers can draw contours in full-frame coords.

    returns dict with keys:
        pupil_center  - (x, y) in full-frame coords or None
        roi_center    - (x, y) in roi-local coords or None
        bbox          - (w, h) of best contour or None
        candidates    - list of dicts sorted by score descending, each with:
                        contour, score, mean_intensity, area
        roi_offset_x  - x offset to convert roi coords → frame coords
        roi_offset_y  - y offset to convert roi coords → frame coords
    """
    empty = {
        'pupil_center': None,
        'roi_center': None,
        'bbox': None,
        'candidates': [],
        'roi_offset_x': 0,
        'roi_offset_y': 0,
    }

    if frame is None:
        return empty

    # convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # crop roi ~ single eye area (same region as detect_pupil_contour)
    h, w = gray.shape
    roi_offset_x = int(w * 0.35)
    roi_offset_y = int(h * 0.4)
    roi = gray[int(h * 0.4):int(h * 0.7), int(w * 0.35):int(w * 0.65)]

    # apply slight blur to reduce noise
    blurred = cv2.GaussianBlur(roi, (3, 3), 0)

    # adaptive threshold based on image brightness
    mean_val = np.mean(blurred)
    min_val = np.min(blurred)

    if min_val > 80:
        threshold_value = mean_val * 0.65
    else:
        threshold_value = max(30, mean_val * 0.4)

    _, thresh = cv2.threshold(blurred, threshold_value, 255, cv2.THRESH_BINARY_INV)

    # morphological operations to clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    # find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        empty['roi_offset_x'] = roi_offset_x
        empty['roi_offset_y'] = roi_offset_y
        return empty

    roi_h, roi_w = roi.shape
    roi_area = roi_h * roi_w

    # filter and score contours
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)

        # size filter
        if area < 20 or area > roi_area * 0.25:
            continue

        x, y, w_box, h_box = cv2.boundingRect(contour)
        aspect_ratio = float(w_box) / h_box if h_box > 0 else 0

        if aspect_ratio < 0.5 or aspect_ratio > 2.0:
            continue

        mask = np.zeros(roi.shape, dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        mean_intensity = cv2.mean(blurred, mask=mask)[0]

        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)

        score = (255 - mean_intensity) * 0.7 + circularity * 50 * 0.3

        candidates.append({
            'contour': contour,
            'score': score,
            'mean_intensity': mean_intensity,
            'area': area,
        })

    candidates.sort(key=lambda x: x['score'], reverse=True)

    result = {
        'candidates': candidates,
        'roi_offset_x': roi_offset_x,
        'roi_offset_y': roi_offset_y,
        'pupil_center': None,
        'roi_center': None,
        'bbox': None,
    }

    if candidates:
        best = candidates[0]
        M = cv2.moments(best['contour'])
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            x, y, w_box, h_box = cv2.boundingRect(best['contour'])
            cx = x + w_box // 2
            cy = y + h_box // 2

        x, y, w_box, h_box = cv2.boundingRect(best['contour'])

        full_cx = cx + roi_offset_x
        full_cy = cy + roi_offset_y

        result['pupil_center'] = (full_cx, full_cy)
        result['roi_center'] = (cx, cy)
        result['bbox'] = (w_box, h_box)

    return result
