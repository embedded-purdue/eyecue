#!/usr/bin/env python3
"""
standalone pupil detection module using contour analysis
- extracted from contour_gaze_tracker.py for reuse across modules
- handles corneal reflections, low-contrast eyes, and varying lighting
- optimized for real-time processing (~2-5ms per frame)
"""

import cv2
import math
import time
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
    # Fast bright-spot detection. Use a local-statistics threshold so dim
    # scenes still clean reflections, while bright scenes do not over-mask.
    mean_val = float(np.mean(roi_gray))
    std_val = float(np.std(roi_gray))
    bright_thresh = int(max(205, min(245, mean_val + 2.2 * std_val)))
    _, bright_mask = cv2.threshold(roi_gray, bright_thresh, 255, cv2.THRESH_BINARY)

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


def _score_candidates_at_threshold(
    roi_processed,
    roi_raw,
    roi_area,
    thresh_val,
    mask_buf,
    seen_centroids,
    *,
    prefer_xy_local=None,
    min_area=30,
    max_area_ratio=0.30,
    aspect_lo=0.55,
    aspect_hi=1.85,
):
    """Find and score contour candidates for one threshold value."""
    _, thresh = cv2.threshold(roi_processed, thresh_val, 255, cv2.THRESH_BINARY_INV)

    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, _KERNEL_3, iterations=3)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, _KERNEL_3, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    roi_h, roi_w = roi_raw.shape[:2]
    roi_diag = math.sqrt(float(roi_w * roi_w + roi_h * roi_h))
    candidates = []

    for contour in contours:
        area = cv2.contourArea(contour)

        if area < min_area or area > roi_area * max_area_ratio:
            continue

        x, y, w_box, h_box = cv2.boundingRect(contour)
        if h_box == 0 or w_box == 0:
            continue
        if w_box > roi_w * 0.70 or h_box > roi_h * 0.70:
            continue
        aspect_ratio = float(w_box) / h_box

        if aspect_ratio < aspect_lo or aspect_ratio > aspect_hi:
            continue

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

        mask_buf[:] = 0
        cv2.drawContours(mask_buf, [contour], -1, 255, -1)
        mean_intensity = cv2.mean(roi_raw, mask=mask_buf)[0]

        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)

        fill_ratio = area / max(1.0, float(w_box * h_box))
        edge_margin = min(x, y, roi_w - (x + w_box), roi_h - (y + h_box))
        edge_penalty = max(0.0, (6.0 - float(edge_margin)) / 6.0) * 8.0
        fill_penalty = abs(fill_ratio - 0.72) * 10.0

        prior_penalty = 0.0
        if prefer_xy_local is not None and roi_diag > 0:
            px, py = float(prefer_xy_local[0]), float(prefer_xy_local[1])
            dist = math.sqrt((float(cx) - px) ** 2 + (float(cy) - py) ** 2)
            prior_penalty = min(10.0, (dist / roi_diag) * 12.0)

        darkness_score = (255 - mean_intensity) * 0.5
        circularity_score = circularity * 50 * 0.25
        area_score = min(area / roi_area * 100, 15) * 0.25
        score = darkness_score + circularity_score + area_score - edge_penalty - fill_penalty - prior_penalty

        sub_cx, sub_cy = _subpixel_center(contour, (cx, cy))

        candidates.append({
            'contour': contour,
            'score': score,
            'mean_intensity': mean_intensity,
            'area': area,
            'circularity': circularity,
            'aspect_ratio': aspect_ratio,
            'fill_ratio': fill_ratio,
            'edge_margin': edge_margin,
            'thresh_val': thresh_val,
            'cx_local': sub_cx,
            'cy_local': sub_cy,
        })

    return candidates


def _find_candidates_fast(roi_processed, roi_raw, roi_area, min_area=30, max_area_ratio=0.30,
                          aspect_lo=0.55, aspect_hi=1.85, prefer_xy_local=None):
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

    candidates = []
    seen_centroids = set()
    mask_buf = _get_mask_buf(roi_raw.shape)

    for thresh_val in thresholds:
        candidates.extend(_score_candidates_at_threshold(
            roi_processed,
            roi_raw,
            roi_area,
            thresh_val,
            mask_buf,
            seen_centroids,
            prefer_xy_local=prefer_xy_local,
            min_area=min_area,
            max_area_ratio=max_area_ratio,
            aspect_lo=aspect_lo,
            aspect_hi=aspect_hi,
        ))

    candidates.sort(key=lambda c: c['score'], reverse=True)

    if not candidates or candidates[0]['score'] < 45:
        std_val = float(np.std(roi_processed))
        low_contrast_thresh = int(max(20, min(230, mean_val - max(8.0, std_val * 0.35))))
        if all(abs(low_contrast_thresh - t) > 10 for t in thresholds):
            candidates.extend(_score_candidates_at_threshold(
                roi_processed,
                roi_raw,
                roi_area,
                low_contrast_thresh,
                mask_buf,
                seen_centroids,
                prefer_xy_local=prefer_xy_local,
                min_area=min_area,
                max_area_ratio=max_area_ratio,
                aspect_lo=aspect_lo,
                aspect_hi=aspect_hi,
            ))

    candidates.sort(key=lambda c: c['score'], reverse=True)
    return candidates


def _subpixel_center(contour, fallback_xy):
    """Sub-pixel pupil center via ellipse fit; falls back to moments/bbox."""
    if len(contour) >= 5:
        try:
            (cx, cy), _axes, _angle = cv2.fitEllipse(contour)
            return float(cx), float(cy)
        except cv2.error:
            pass
    return float(fallback_xy[0]), float(fallback_xy[1])


def _pick_candidate(candidates, prefer_xy_local=None, score_tie_ratio=0.85):
    """
    Pick the best candidate from a *score-sorted* list.

    Without `prefer_xy_local`, return the top-scored candidate.
    With it, consider all candidates whose score is within `score_tie_ratio`
    of the top score, and among those pick the one closest to the reference
    point (in roi-local coords). This kills frame-to-frame candidate
    swapping when several blobs (pupil, lash shadow, eyebrow) score
    similarly.
    """
    if not candidates:
        return None
    if prefer_xy_local is None:
        return candidates[0]
    top_score = candidates[0]['score']
    cutoff = top_score * score_tie_ratio
    pool = [c for c in candidates if c['score'] >= cutoff]
    if len(pool) == 1:
        return pool[0]
    rx, ry = float(prefer_xy_local[0]), float(prefer_xy_local[1])

    def _dist2(c):
        dx = c['cx_local'] - rx
        dy = c['cy_local'] - ry
        return dx * dx + dy * dy

    return min(pool, key=_dist2)


def _extract_best(candidates, roi_offset_x, roi_offset_y, prefer_xy_local=None):
    """Extract pupil center from best candidate. Shared by both public functions."""
    if not candidates:
        return None, None, None

    best = _pick_candidate(candidates, prefer_xy_local=prefer_xy_local)
    if best is None:
        return None, None, None
    M = cv2.moments(best['contour'])
    if M["m00"] != 0:
        cx_int = int(M["m10"] / M["m00"])
        cy_int = int(M["m01"] / M["m00"])
    else:
        x, y, w_box, h_box = cv2.boundingRect(best['contour'])
        cx_int = x + w_box // 2
        cy_int = y + h_box // 2

    sub_cx, sub_cy = _subpixel_center(best['contour'], (cx_int, cy_int))

    x, y, w_box, h_box = cv2.boundingRect(best['contour'])

    full_cx = int(round(sub_cx + roi_offset_x))
    full_cy = int(round(sub_cy + roi_offset_y))

    return (full_cx, full_cy), (int(sub_cx), int(sub_cy)), (w_box, h_box)


def _preprocess_roi(gray, window=None):
    """
    Crop ROI, remove reflections, enhance contrast, blur.
    If `window` is given as (x0, y0, x1, y1) in full-frame coords, use that
    rectangle (clamped) instead of the default centered ROI. Returns
    (roi_raw, roi_processed, roi_offset_x, roi_offset_y).
    """
    h, w = gray.shape
    if window is None:
        roi_offset_x = int(w * 0.25)
        roi_offset_y = int(h * 0.3)
        roi = gray[int(h * 0.3):int(h * 0.75), int(w * 0.25):int(w * 0.75)]
    else:
        x0, y0, x1, y1 = window
        x0 = max(0, int(x0)); y0 = max(0, int(y0))
        x1 = min(w, int(x1)); y1 = min(h, int(y1))
        if x1 - x0 < 8 or y1 - y0 < 8:
            return _preprocess_roi(gray, window=None)
        roi_offset_x = x0
        roi_offset_y = y0
        roi = gray[y0:y1, x0:x1]

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


# ── stateful tracking + smoothing ───────────────────────────────────────


def _candidate_confidence(cand, roi_area):
    """Map a raw candidate score into a [0,1] confidence."""
    darkness = max(0.0, (255.0 - cand['mean_intensity'])) / 255.0
    circ = max(0.0, min(1.0, cand['circularity']))
    area_frac = cand['area'] / max(1.0, roi_area)
    # pupil typically occupies 1–15% of the search ROI
    area_score = 1.0 - min(1.0, abs(area_frac - 0.05) / 0.10)
    area_score = max(0.0, area_score)
    fill_ratio = max(0.0, min(1.0, cand.get('fill_ratio', 0.72)))
    fill_score = 1.0 - min(1.0, abs(fill_ratio - 0.72) / 0.45)
    edge_score = 1.0 if cand.get('edge_margin', 6) >= 3 else 0.75
    return 0.45 * darkness + 0.30 * circ + 0.15 * area_score + 0.10 * fill_score * edge_score


class PupilTracker:
    """
    Stateful pupil detector with temporal prior, jump rejection, and a
    confidence score per detection.

    Strategy:
      * If we have a recent confident detection, search a small window
        around it first. This is faster and avoids being distracted by
        eyebrow/lash blobs elsewhere in the frame.
      * Fall back to the full default ROI on miss, or after several
        consecutive low-confidence frames.
      * Reject sudden jumps unless they persist for `jump_confirm_frames`
        frames in a row (handles the case where the pupil really did
        snap to a new location, e.g. saccade).
    """

    def __init__(
        self,
        search_half_w=80,
        search_half_h=60,
        max_jump_px=120,
        jump_confirm_frames=2,
        miss_reset_frames=4,
        min_confidence=0.22,
    ):
        self.search_half_w = int(search_half_w)
        self.search_half_h = int(search_half_h)
        self.max_jump_px = float(max_jump_px)
        self.jump_confirm_frames = int(jump_confirm_frames)
        self.miss_reset_frames = int(miss_reset_frames)
        self.min_confidence = float(min_confidence)

        self.last_center = None  # (x, y) full-frame
        self.last_bbox = None
        self.last_confidence = 0.0
        self.consecutive_misses = 0
        self._pending_jump = None  # (x, y)
        self._pending_count = 0

    def reset(self):
        self.last_center = None
        self.last_bbox = None
        self.last_confidence = 0.0
        self.consecutive_misses = 0
        self._pending_jump = None
        self._pending_count = 0

    def _detect_in_window(self, gray, window, prefer_full_xy=None):
        roi_raw, roi_processed, ox, oy = _preprocess_roi(gray, window=window)
        roi_area = roi_raw.shape[0] * roi_raw.shape[1]
        prefer_local = None
        if prefer_full_xy is not None:
            prefer_local = (prefer_full_xy[0] - ox, prefer_full_xy[1] - oy)
        cands = _find_candidates_fast(roi_processed, roi_raw, roi_area, prefer_xy_local=prefer_local)
        if not cands:
            return None, 0.0, None
        # convert preferred reference (full-frame) to roi-local if given
        center, _roi_center, bbox = _extract_best(cands, ox, oy, prefer_xy_local=prefer_local)
        # confidence: report on the candidate we actually picked (which may
        # not be cands[0] when proximity tie-breaking kicks in).
        chosen = _pick_candidate(cands, prefer_xy_local=prefer_local)
        conf = _candidate_confidence(chosen if chosen is not None else cands[0], roi_area)
        return center, conf, bbox

    def update(self, frame):
        """
        Run detection on `frame`. Returns dict:
          center: (x, y) in full-frame coords, or None
          confidence: float in [0, 1]
          bbox: (w, h) or None
          source: 'window' | 'full' | 'hold' | 'miss'
        """
        if frame is None:
            return {'center': None, 'confidence': 0.0, 'bbox': None, 'source': 'miss'}

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        # 1. try a tight window around the last known position; bias the
        #    in-window candidate selection toward last_center so we don't
        #    swap to a similar-scoring but spatially-different blob.
        center = None
        conf = 0.0
        bbox = None
        source = 'full'
        if self.last_center is not None:
            lx, ly = self.last_center
            window = (
                lx - self.search_half_w, ly - self.search_half_h,
                lx + self.search_half_w, ly + self.search_half_h,
            )
            center, conf, bbox = self._detect_in_window(
                gray, window, prefer_full_xy=self.last_center
            )
            if center is not None and conf >= self.min_confidence:
                source = 'window'

        # 2. fall back to full default ROI on miss / low confidence
        if center is None or conf < self.min_confidence:
            full_center, full_conf, full_bbox = self._detect_in_window(
                gray, None, prefer_full_xy=self.last_center
            )
            if full_center is not None and full_conf >= conf:
                center, conf, bbox = full_center, full_conf, full_bbox
                source = 'full'

        # 3. handle the no-detection case
        if center is None or conf < self.min_confidence:
            self.consecutive_misses += 1
            if self.consecutive_misses >= self.miss_reset_frames:
                self.reset()
                return {'center': None, 'confidence': 0.0, 'bbox': None, 'source': 'miss'}
            # short-term hold: keep returning last position so the cursor
            # doesn't snap to centre on a single dropped frame
            if self.last_center is not None:
                return {
                    'center': self.last_center,
                    'confidence': self.last_confidence * 0.5,
                    'bbox': self.last_bbox,
                    'source': 'hold',
                }
            return {'center': None, 'confidence': 0.0, 'bbox': None, 'source': 'miss'}

        # 4. jump rejection: confirm large jumps over multiple frames
        if self.last_center is not None:
            dx = center[0] - self.last_center[0]
            dy = center[1] - self.last_center[1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > self.max_jump_px:
                if self._pending_jump is None:
                    self._pending_jump = center
                    self._pending_count = 1
                else:
                    pdx = center[0] - self._pending_jump[0]
                    pdy = center[1] - self._pending_jump[1]
                    if math.sqrt(pdx * pdx + pdy * pdy) <= self.max_jump_px:
                        self._pending_count += 1
                        self._pending_jump = center
                    else:
                        # jump target itself jumped — restart confirmation
                        self._pending_jump = center
                        self._pending_count = 1

                if self._pending_count < self.jump_confirm_frames:
                    # not confirmed yet — hold last
                    return {
                        'center': self.last_center,
                        'confidence': self.last_confidence * 0.7,
                        'bbox': self.last_bbox,
                        'source': 'hold',
                    }
                # confirmed — accept the new position
                self._pending_jump = None
                self._pending_count = 0
            else:
                self._pending_jump = None
                self._pending_count = 0

        self.last_center = center
        self.last_bbox = bbox
        self.last_confidence = conf
        self.consecutive_misses = 0

        return {'center': center, 'confidence': conf, 'bbox': bbox, 'source': source}


class OneEuroFilter:
    """
    1€ filter (Casiez et al. 2012). Adapts smoothing to motion speed:
      * heavy smoothing when slow / still → kills jitter on fixations
      * light smoothing when fast → minimal lag during saccades

    `mincutoff` (Hz) sets the floor; `beta` controls how quickly we open
    the cutoff with speed. Sensible defaults for a ~30 fps pixel signal.
    """

    def __init__(self, mincutoff=2.5, beta=0.15, dcutoff=1.5):
        self.mincutoff = float(mincutoff)
        self.beta = float(beta)
        self.dcutoff = float(dcutoff)
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self):
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, x, t=None):
        if t is None:
            t = time.monotonic()
        if self._t_prev is None or self._x_prev is None:
            self._t_prev = t
            self._x_prev = float(x)
            self._dx_prev = 0.0
            return float(x)
        dt = max(1e-6, t - self._t_prev)
        dx = (float(x) - self._x_prev) / dt
        a_d = self._alpha(self.dcutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        cutoff = self.mincutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * float(x) + (1.0 - a) * self._x_prev
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


class OneEuroFilter2D:
    """Convenience wrapper: independent 1€ filters on x and y."""

    def __init__(self, mincutoff=2.5, beta=0.15, dcutoff=1.5):
        self._fx = OneEuroFilter(mincutoff, beta, dcutoff)
        self._fy = OneEuroFilter(mincutoff, beta, dcutoff)

    def reset(self):
        self._fx.reset()
        self._fy.reset()

    def __call__(self, xy, t=None):
        if t is None:
            t = time.monotonic()
        return self._fx(xy[0], t), self._fy(xy[1], t)
