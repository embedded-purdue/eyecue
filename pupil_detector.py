#!/usr/bin/env python3
"""
standalone pupil detection module
uses OrloskyPupil's ellipse-fitting algorithm:
  - finds darkest region in frame
  - applies multi-level thresholding (strict / medium / relaxed)
  - fits and scores ellipses to select the best pupil boundary
  - returns (pupil_center, bbox)
"""

from OrloskyPupil import process_frame as orlosky_process_frame


def detect_pupil_contour(frame):
    """
    Detect pupil center using OrloskyPupil's ellipse-fitting method.

    Returns:
        pupil_center : (x, y) int tuple in frame pixel coords, or None
        bbox         : (w, h) int tuple of ellipse axes, or None
    """
    rotated_rect = orlosky_process_frame(frame)

    # orlosky_process_frame returns ((0,0),(0,0),0) when no pupil is found
    center, axes, _angle = rotated_rect
    cx, cy = center
    aw, ah = axes

    if cx == 0 and cy == 0 and aw == 0 and ah == 0:
        return None, None

    pupil_center = (int(cx), int(cy))
    bbox = (int(aw), int(ah))

    return pupil_center, bbox
