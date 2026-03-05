from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    import cv2
    import numpy as np

    from app.services.contour_pupil_processor import ContourPupilFrameProcessor

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


def _encode_jpeg(frame: "np.ndarray") -> bytes:
    ok, out = cv2.imencode('.jpg', frame)
    if not ok:
        raise RuntimeError('failed to encode test frame')
    return out.tobytes()


@unittest.skipUnless(DEPS_AVAILABLE, "opencv/numpy are required for contour processor tests")
class ContourPupilProcessorTest(unittest.TestCase):
    def test_detection_maps_to_screen(self) -> None:
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1920, 1080))
        frame = np.full((240, 320, 3), 255, dtype=np.uint8)
        frame_bytes = _encode_jpeg(frame)

        with patch('app.services.contour_pupil_processor.detect_pupil_contour') as mock_detect:
            mock_detect.return_value = ((160, 120), (0, 0), (20, 30))
            result = processor.process_frame(frame_bytes, {"width": 320, "height": 240})

        self.assertTrue(result['ok'])
        self.assertEqual(result['cursor']['x'], 960)
        self.assertEqual(result['cursor']['y'], 540)
        self.assertEqual(result['cursor']['confidence'], 0.8)
        self.assertEqual(result['diagnostics']['reason'], 'detected')
        self.assertTrue(result['diagnostics']['detection_ok'])
        self.assertFalse(result['diagnostics']['used_fallback'])

    def test_no_detection_holds_last_cursor(self) -> None:
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (640, 480))
        frame = np.full((120, 160, 3), 255, dtype=np.uint8)
        frame_bytes = _encode_jpeg(frame)

        with patch('app.services.contour_pupil_processor.detect_pupil_contour') as mock_detect:
            mock_detect.side_effect = [((40, 30), (0, 0), (10, 10)), (None, None, None)]
            first = processor.process_frame(frame_bytes, {"width": 160, "height": 120})
            second = processor.process_frame(frame_bytes, {"width": 160, "height": 120})

        self.assertEqual(first['cursor']['x'], 160)
        self.assertEqual(first['cursor']['y'], 120)
        self.assertEqual(second['cursor']['x'], first['cursor']['x'])
        self.assertEqual(second['cursor']['y'], first['cursor']['y'])
        self.assertEqual(second['cursor']['confidence'], 0.1)
        self.assertEqual(second['diagnostics']['reason'], 'no_detection_hold_last')
        self.assertFalse(second['diagnostics']['detection_ok'])
        self.assertTrue(second['diagnostics']['used_fallback'])

    def test_first_no_detection_uses_center(self) -> None:
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (800, 600))
        frame = np.full((120, 160, 3), 255, dtype=np.uint8)
        frame_bytes = _encode_jpeg(frame)

        with patch('app.services.contour_pupil_processor.detect_pupil_contour') as mock_detect:
            mock_detect.return_value = (None, None, None)
            result = processor.process_frame(frame_bytes, {"width": 160, "height": 120})

        self.assertEqual(result['cursor']['x'], 400)
        self.assertEqual(result['cursor']['y'], 300)
        self.assertEqual(result['cursor']['confidence'], 0.1)
        self.assertEqual(result['diagnostics']['reason'], 'no_detection_center')

    def test_decode_failure_falls_back_and_holds(self) -> None:
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 700))

        first = processor.process_frame(b'not-a-jpeg', {"width": 160, "height": 120})
        second = processor.process_frame(b'also-not-a-jpeg', {"width": 160, "height": 120})

        self.assertEqual(first['cursor']['x'], 500)
        self.assertEqual(first['cursor']['y'], 350)
        self.assertEqual(first['diagnostics']['reason'], 'decode_failed_center')
        self.assertEqual(second['cursor']['x'], first['cursor']['x'])
        self.assertEqual(second['cursor']['y'], first['cursor']['y'])
        self.assertEqual(second['diagnostics']['reason'], 'decode_failed_hold_last')


if __name__ == '__main__':
    unittest.main()
