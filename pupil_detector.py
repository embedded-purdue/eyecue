#!/usr/bin/env python3
"""
standalone pupil detection module using contour analysis
- extracted from contour_gaze_tracker.py for reuse across modules
- handles corneal reflections, low-contrast eyes, and varying lighting
- optimized for real-time processing (~2-5ms per frame)
"""

import cv2
import numpy as np

# ── module-level singletons (avoid per-frame allocation) ────────────────
_CLAHE = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
_KERNEL_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
_KERNEL_5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

# reusable mask buffer — lazily sized on first use
_mask_buf = None  # type: np.ndarray | None


def _get_mask_buf(shape):
    """return a pre-allocated zero mask matching *shape*, reusing memory."""
    global _mask_buf
    if _mask_buf is None or _mask_buf.shape != shape:
        _mask_buf = np.zeros(shape, dtype=np.uint8)
    else:
        _mask_buf[:] = 0
    return _mask_buf


def _remove_reflections_fast(roi_gray):
    """
    Remove specular reflections using fast morphological fill.
    Much cheaper than cv2.inpaint (~0.3ms vs ~20ms).
    """
    # fast bright-spot detection: anything above fixed high threshold
    # avoids np.percentile which sorts the entire array
    _, bright_mask = cv2.threshold(roi_gray, 220, 255, cv2.THRESH_BINARY)

    # if no bright spots, skip entirely
    if cv2.countNonZero(bright_mask) == 0:
        return roi_gray

    # dilate bright spots slightly
    bright_mask = cv2.dilate(bright_mask, _KERNEL_5, iterations=1)

    # fill bright spots with local median (fast alternative to inpaint)
    median = cv2.medianBlur(roi_gray, 7)
    cleaned = roi_gray.copy()
    cleaned[bright_mask > 0] = median[bright_mask > 0]
    return cleaned


def _enhance_contrast(roi_gray):
    """Apply cached CLAHE to boost pupil-iris contrast."""
    return _CLAHE.apply(roi_gray)


def _find_candidates_fast(roi_processed, roi_raw, roi_area, min_area=8, max_area_ratio=0.40,
                          aspect_lo=0.3, aspect_hi=3.0):
    """
    Find and score contour candidates using 2 threshold levels (down from 4).
    Pre-allocates mask buffer to avoid per-contour np.zeros().
    """
    mean_val = np.mean(roi_processed)
    min_val = np.min(roi_processed)

    # build just 2 thresholds: one adaptive + one Otsu
    if min_val > 80:
        adaptive_thresh = int(mean_val * 0.65)
    else:
        adaptive_thresh = int(max(25, mean_val * 0.4))

    otsu_val, _ = cv2.threshold(roi_processed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    otsu_thresh = int(otsu_val)

    # deduplicate — if they're very close, just use one
    thresholds = [adaptive_thresh]
    if abs(otsu_thresh - adaptive_thresh) > 15:
        thresholds.append(otsu_thresh)

    seen_centroids = set()
    candidates = []
    mask_buf = _get_mask_buf(roi_raw.shape)

    for thresh_val in thresholds:
        _, thresh = cv2.threshold(roi_processed, thresh_val, 255, cv2.THRESH_BINARY_INV)

        # morphological cleanup
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, _KERNEL_3, iterations=3)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, _KERNEL_3, iterations=1)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)

            if area < min_area or area > roi_area * max_area_ratio:
                continue

            x, y, w_box, h_box = cv2.boundingRect(contour)
            if h_box == 0:
                continue
            aspect_ratio = float(w_box) / h_box

            if aspect_ratio < aspect_lo or aspect_ratio > aspect_hi:
                continue

            # centroid for dedup
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
            else:
                cx = x + w_box // 2
                cy = y + h_box // 2

            centroid_key = (cx // 5, cy // 5)
            if centroid_key in seen_centroids:
                continue
            seen_centroids.add(centroid_key)

            # mean intensity using reusable mask buffer
            mask_buf[:] = 0
            cv2.drawContours(mask_buf, [contour], -1, 255, -1)
            mean_intensity = cv2.mean(roi_raw, mask=mask_buf)[0]

            # circularity
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)

            # scoring
            darkness_score = (255 - mean_intensity) * 0.5
            circularity_score = circularity * 50 * 0.25
            area_score = min(area / roi_area * 100, 15) * 0.25
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


def _extract_best(candidates, roi_offset_x, roi_offset_y):
    """Extract pupil center from best candidate. Shared by both public functions."""
    if not candidates:
        return None, None, None

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

    return (full_cx, full_cy), (cx, cy), (w_box, h_box)


def _preprocess_roi(gray):
    """Crop ROI, remove reflections, enhance contrast, blur. Returns (roi_raw, roi_processed, offsets)."""
    h, w = gray.shape
    roi_offset_x = int(w * 0.25)
    roi_offset_y = int(h * 0.3)
    roi = gray[int(h * 0.3):int(h * 0.75), int(w * 0.25):int(w * 0.75)]

    cleaned = _remove_reflections_fast(roi)
    enhanced = _enhance_contrast(cleaned)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)

    return roi, blurred, roi_offset_x, roi_offset_y


def detect_pupil_contour(frame):
    """Pupil detection using darkest region with size filtering. No debug prints."""
    if frame is None:
        return None, None, None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi_raw, roi_processed, roi_offset_x, roi_offset_y = _preprocess_roi(gray)

    roi_area = roi_raw.shape[0] * roi_raw.shape[1]
    candidates = _find_candidates_fast(roi_processed, roi_raw, roi_area)

    if not candidates:
        return None, None, None

    return _extract_best(candidates, roi_offset_x, roi_offset_y)


def detect_pupil_contour_candidates(frame):
    """
    Pupil detection that returns ALL scored candidates (sorted best-to-worst)
    plus the roi offset so callers can draw contours in full-frame coords.

    Returns dict with keys:
        pupil_center  - (x, y) in full-frame coords or None
        roi_center    - (x, y) in roi-local coords or None
        bbox          - (w, h) of best contour or None
        candidates    - list of dicts sorted by score descending
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

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi_raw, roi_processed, roi_offset_x, roi_offset_y = _preprocess_roi(gray)

    roi_area = roi_raw.shape[0] * roi_raw.shape[1]
    candidates = _find_candidates_fast(roi_processed, roi_raw, roi_area)

    result = {
        'candidates': candidates,
        'roi_offset_x': roi_offset_x,
        'roi_offset_y': roi_offset_y,
        'pupil_center': None,
        'roi_center': None,
        'bbox': None,
    }

    pupil_center, roi_center, bbox = _extract_best(candidates, roi_offset_x, roi_offset_y)
    if pupil_center is not None:
        result['pupil_center'] = pupil_center
        result['roi_center'] = roi_center
        result['bbox'] = bbox

    return result
