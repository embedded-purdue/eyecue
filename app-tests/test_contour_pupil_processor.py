import unittest
from unittest.mock import patch

import cv2
import numpy as np

from app.services.contour_pupil_processor import ContourPupilFrameProcessor


def _jpeg_frame(width: int = 200, height: int = 100) -> bytes:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("failed to encode test frame")
    return encoded.tobytes()


class ContourPupilFrameProcessorTests(unittest.TestCase):
    def test_detection_success_uses_gaze_mapping(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch(
            "app.services.contour_pupil_processor.detect_pupil_contour",
            return_value=((100, 50), (0, 0), (12, 10)),
        ), patch(
            "app.services.contour_pupil_processor.extract_contour_gaze_data",
            return_value={
                "single_gaze_vector": [0.1, 0.2, 0.9],
                "single_angles": [8.0, -2.0],
                "single_offset": [0.05, -0.02],
            },
        ) as gaze_mock, patch(
            "app.services.contour_pupil_processor.map_gaze_angles_to_screen",
            return_value=(111, 222),
        ) as map_mock:
            result = processor.process_frame(frame_bytes, {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["cursor"], {"x": 111, "y": 222, "confidence": 0.8})

        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["reason"], "detected_gaze_mapped")
        self.assertEqual(diagnostics["mapping_source"], "gaze_angles_cursorcontroller")
        self.assertFalse(diagnostics["used_fallback"])
        self.assertEqual(diagnostics["single_angles"], [8.0, -2.0])
        self.assertEqual(diagnostics["single_offset"], [0.05, -0.02])
        self.assertEqual(diagnostics["single_gaze_vector"], [0.1, 0.2, 0.9])

        gaze_mock.assert_called_once()
        map_mock.assert_called_once_with(
            angle_h=8.0,
            angle_v=-2.0,
            screen_width=1000,
            screen_height=500,
        )

    def test_detection_success_falls_back_to_linear_on_gaze_error(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch(
            "app.services.contour_pupil_processor.detect_pupil_contour",
            return_value=((20, 40), (0, 0), (10, 10)),
        ), patch(
            "app.services.contour_pupil_processor.extract_contour_gaze_data",
            side_effect=RuntimeError("gaze exploded"),
        ), patch(
            "app.services.contour_pupil_processor.map_gaze_angles_to_screen"
        ) as map_mock:
            result = processor.process_frame(frame_bytes, {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["cursor"], {"x": 100, "y": 200, "confidence": 0.8})

        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["reason"], "detected_linear_fallback_gaze_error")
        self.assertEqual(diagnostics["mapping_source"], "frame_linear_fallback")
        self.assertTrue(diagnostics["used_fallback"])
        self.assertIn("gaze_exception:", diagnostics.get("gaze_error", ""))
        map_mock.assert_not_called()

    def test_no_detection_uses_center_then_hold_last(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1200, 800))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch(
            "app.services.contour_pupil_processor.detect_pupil_contour",
            side_effect=[(None, None, None), (None, None, None)],
        ):
            first = processor.process_frame(frame_bytes, {})
            second = processor.process_frame(frame_bytes, {})

        self.assertTrue(first["ok"])
        self.assertEqual(first["cursor"], {"x": 600, "y": 400, "confidence": 0.1})
        self.assertEqual(first["diagnostics"]["reason"], "no_detection_center")
        self.assertTrue(first["diagnostics"]["used_fallback"])

        self.assertTrue(second["ok"])
        self.assertEqual(second["cursor"], {"x": 600, "y": 400, "confidence": 0.1})
        self.assertEqual(second["diagnostics"]["reason"], "no_detection_hold_last")
        self.assertTrue(second["diagnostics"]["used_fallback"])


if __name__ == "__main__":
    unittest.main()
