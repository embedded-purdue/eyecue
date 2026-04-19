#!/usr/bin/env python3
"""
standalone pupil detection module using contour analysis
- extracted from contour_gaze_tracker.py for reuse across modules
- handles corneal reflections, low-contrast eyes, and varying lighting
"""

import cv2
import numpy as np


def _remove_reflections(roi_gray):
    """
    remove specular reflections (corneal glints) from the eye roi.
    reflections are small, very bright spots that break up the dark pupil region.
    we detect them and inpaint over them with surrounding intensity.
    """
    # find very bright spots (top ~5% intensity or anything near white)
    bright_thresh = max(200, np.percentile(roi_gray, 95))
    _, bright_mask = cv2.threshold(roi_gray, bright_thresh, 255, cv2.THRESH_BINARY)

    # dilate the bright spots slightly so inpainting covers them fully
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    bright_mask = cv2.dilate(bright_mask, kernel, iterations=1)

    # inpaint over reflections
    cleaned = cv2.inpaint(roi_gray, bright_mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    return cleaned


def _enhance_contrast(roi_gray):
    """
    apply CLAHE (contrast-limited adaptive histogram equalization) to boost
    pupil-iris contrast, which is often very low in camera feeds.
    """
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
    return clahe.apply(roi_gray)


def _find_candidates(roi_processed, roi_raw, roi_area, min_area=8, max_area_ratio=0.40,
                     aspect_lo=0.3, aspect_hi=3.0):
    """
    threshold, clean, find contours, and score them.
    tries multiple threshold levels and merges the candidate lists.
    """
    mean_val = np.mean(roi_processed)
    min_val = np.min(roi_processed)

    # build a set of thresholds to try — more chances to capture the pupil
    thresholds = []
    if min_val > 80:
        # overexposed: try several cuts relative to the mean
        thresholds = [mean_val * f for f in (0.75, 0.65, 0.55)]
    else:
        # normal: range from conservative to aggressive
        base = max(25, mean_val * 0.4)
        thresholds = [base, base * 1.3, base * 0.7]

    # also always try an Otsu threshold as a safety net
    otsu_val, _ = cv2.threshold(roi_processed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    thresholds.append(otsu_val)

    # deduplicate and sort
    thresholds = sorted(set(int(t) for t in thresholds if 5 < t < 250))

    seen_centroids = set()  # avoid near-duplicate contours across thresholds
    candidates = []

    for thresh_val in thresholds:
        _, thresh = cv2.threshold(roi_processed, thresh_val, 255, cv2.THRESH_BINARY_INV)

        # morphological cleanup — close first to merge reflection-split fragments,
        # then open to remove noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)

            # relaxed size filter
            if area < min_area or area > roi_area * max_area_ratio:
                continue

            x, y, w_box, h_box = cv2.boundingRect(contour)
            if h_box == 0:
                continue
            aspect_ratio = float(w_box) / h_box

            # relaxed aspect ratio — pupils can look elliptical from an angle
            if aspect_ratio < aspect_lo or aspect_ratio > aspect_hi:
                continue

            # compute centroid for dedup
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
            else:
                cx = x + w_box // 2
                cy = y + h_box // 2

            # skip near-duplicate centroids (within 5px) from different thresholds
            centroid_key = (cx // 5, cy // 5)
            if centroid_key in seen_centroids:
                continue
            seen_centroids.add(centroid_key)

            # mean intensity of this blob in the original (non-enhanced) roi
            mask = np.zeros(roi_raw.shape, dtype=np.uint8)
            cv2.drawContours(mask, [contour], -1, 255, -1)
            mean_intensity = cv2.mean(roi_raw, mask=mask)[0]

            # circularity
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)

            # scoring: darkness is most important, circularity is a bonus,
            # and area gets a small bonus (prefer larger blobs — the real pupil
            # is usually the largest dark blob)
            darkness_score = (255 - mean_intensity) * 0.5
            circularity_score = circularity * 50 * 0.25
            area_score = min(area / roi_area * 100, 15) * 0.25  # caps at 15 points
            score = darkness_score + circularity_score + area_score

            candidates.append({
                'contour': contour,
                'score': score,
                'mean_intensity': mean_intensity,
                'area': area,
                'circularity': circularity,
                'aspect_ratio': aspect_ratio,
                'thresh_val': thresh_val,
            })

    candidates.sort(key=lambda c: c['score'], reverse=True)
    return candidates


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
    
    # crop roi — wider region to avoid clipping the pupil near edges
    h, w = gray.shape
    roi = gray[int(h*0.3):int(h*0.75), int(w*0.25):int(w*0.75)]
    print(f"[DEBUG] ROI shape: {roi.shape}")

    # remove specular reflections before processing
    cleaned = _remove_reflections(roi)

    # enhance contrast so the pupil stands out
    enhanced = _enhance_contrast(cleaned)

    # apply blur to reduce noise (on the enhanced image)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)

    roi_h, roi_w = roi.shape
    roi_area = roi_h * roi_w

    # find candidates using multi-threshold approach
    candidates = _find_candidates(blurred, roi, roi_area)

    print(f"[DEBUG] Found {len(candidates)} valid candidates")

    if not candidates:
        print("[DEBUG] No valid candidates - returning None")
        return None, None, None

    best = candidates[0]
    print(f"[DEBUG] Best candidate - score: {best['score']:.1f}, area: {best['area']:.0f}, "
          f"intensity: {best['mean_intensity']:.1f}, circularity: {best['circularity']:.2f}")
    
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
    
    # convert to full frame coords (matching the wider ROI offsets)
    full_cx = cx + int(w*0.25)
    full_cy = cy + int(h*0.3)

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

    # crop roi — wider region (matches detect_pupil_contour)
    h, w = gray.shape
    roi_offset_x = int(w * 0.25)
    roi_offset_y = int(h * 0.3)
    roi = gray[int(h * 0.3):int(h * 0.75), int(w * 0.25):int(w * 0.75)]

    # remove specular reflections
    cleaned = _remove_reflections(roi)

    # enhance contrast
    enhanced = _enhance_contrast(cleaned)

    # blur
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)

    roi_h, roi_w = roi.shape
    roi_area = roi_h * roi_w

    # find candidates using multi-threshold approach
    candidates = _find_candidates(blurred, roi, roi_area)

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
