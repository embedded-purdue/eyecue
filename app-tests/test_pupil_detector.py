import unittest

import cv2
import numpy as np

from pupil_detector import (
    _pick_candidate,
    _remove_reflections_fast,
    detect_pupil_contour,
    detect_pupil_contour_candidates,
)


def _synthetic_eye(
    *,
    pupil=(160, 120),
    pupil_radius=18,
    background=150,
    iris=120,
    pupil_value=25,
    lash_blob=False,
    reflection=False,
):
    frame = np.full((240, 320, 3), background, dtype=np.uint8)
    cv2.ellipse(frame, (160, 120), (90, 55), 0, 0, 360, (iris, iris, iris), -1)
    if lash_blob:
        cv2.rectangle(frame, (82, 74), (238, 86), (20, 20, 20), -1)
    cv2.circle(frame, pupil, pupil_radius, (pupil_value, pupil_value, pupil_value), -1)
    if reflection:
        cv2.circle(frame, (pupil[0] - 5, pupil[1] - 4), 4, (255, 255, 255), -1)
    return frame


class PupilDetectorTests(unittest.TestCase):
    def test_dark_round_pupil_beats_lash_blob(self):
        frame = _synthetic_eye(lash_blob=True)

        center, _roi_center, bbox = detect_pupil_contour(frame)

        self.assertIsNotNone(center)
        self.assertLess(abs(center[0] - 160), 4)
        self.assertLess(abs(center[1] - 120), 4)
        self.assertGreaterEqual(bbox[0], 25)
        self.assertGreaterEqual(bbox[1], 25)

    def test_candidate_near_previous_center_wins_when_scores_are_close(self):
        candidates = [
            {"score": 100.0, "cx_local": 20.0, "cy_local": 20.0},
            {"score": 92.0, "cx_local": 80.0, "cy_local": 80.0},
        ]

        picked = _pick_candidate(candidates, prefer_xy_local=(78, 82), score_tie_ratio=0.90)

        self.assertIs(picked, candidates[1])

    def test_low_contrast_pupil_is_detected(self):
        frame = _synthetic_eye(background=128, iris=116, pupil_value=92)

        result = detect_pupil_contour_candidates(frame)

        self.assertIsNotNone(result["pupil_center"])
        self.assertLess(abs(result["pupil_center"][0] - 160), 5)
        self.assertLess(abs(result["pupil_center"][1] - 120), 5)
        self.assertGreaterEqual(len(result["candidates"]), 1)

    def test_reflection_cleanup_preserves_pupil_detection(self):
        frame = _synthetic_eye(reflection=True)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        cleaned = _remove_reflections_fast(gray)
        center, _roi_center, _bbox = detect_pupil_contour(frame)

        self.assertLess(cleaned[120, 160], 80)
        self.assertIsNotNone(center)
        self.assertLess(abs(center[0] - 160), 5)
        self.assertLess(abs(center[1] - 120), 5)


if __name__ == "__main__":
    unittest.main()
