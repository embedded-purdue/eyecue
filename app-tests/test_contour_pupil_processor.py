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


def _track_hit(center, bbox=(12, 10), confidence=0.85, source="full"):
    return {"center": center, "bbox": bbox, "confidence": confidence, "source": source}


def _track_miss():
    return {"center": None, "bbox": None, "confidence": 0.0, "source": "miss"}


def _ready_baseline(processor, center=(100, 50)):
    processor._baseline_pupil_center = (float(center[0]), float(center[1]))
    processor._baseline_samples = [center] * processor._baseline_required_samples


class ContourPupilFrameProcessorTests(unittest.TestCase):
    def test_initial_detection_collects_baseline_before_mapping(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            return_value=_track_hit((100, 50)),
        ), patch.object(
            processor._gaze_tracker,
            "extract_gaze_numbers",
        ) as gaze_mock, patch(
            "app.services.contour_pupil_processor.map_gaze_angles_to_screen",
        ) as map_mock:
            result = processor.process_frame(frame_bytes, {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["cursor"]["x"], 500)
        self.assertEqual(result["cursor"]["y"], 250)
        self.assertAlmostEqual(result["cursor"]["confidence"], 0.2, places=4)

        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["reason"], "baseline_collecting")
        self.assertEqual(diagnostics["mapping_source"], "baseline_collecting")
        self.assertTrue(diagnostics["used_fallback"])
        self.assertAlmostEqual(diagnostics["confidence"], 0.85, places=4)
        self.assertEqual(diagnostics["tracker_source"], "full")
        self.assertEqual(diagnostics["raw_pupil_center"], {"x": 100, "y": 50})
        self.assertEqual(diagnostics["smoothed_pupil_center"], {"x": 100, "y": 50})
        self.assertTrue(diagnostics["frame_mirrored"])
        self.assertFalse(diagnostics["baseline_ready"])
        self.assertEqual(diagnostics["baseline_sample_count"], 1)
        self.assertIsNone(diagnostics["baseline_pupil_center"])
        self.assertIsNone(diagnostics["baseline_offset"])
        self.assertGreater(diagnostics["projection_half_fov_deg"], 0)

        gaze_mock.assert_not_called()
        map_mock.assert_not_called()

    def test_detection_success_falls_back_to_linear_on_gaze_error(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        _ready_baseline(processor, center=(20, 40))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            return_value=_track_hit((20, 40), bbox=(10, 10)),
        ), patch.object(
            processor,
            "_map_with_baseline",
            return_value=None,
        ), patch.object(
            processor._gaze_tracker,
            "extract_gaze_numbers",
            side_effect=RuntimeError("gaze exploded"),
        ), patch(
            "app.services.contour_pupil_processor.map_gaze_angles_to_screen"
        ) as map_mock:
            result = processor.process_frame(frame_bytes, {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["cursor"]["x"], 100)
        self.assertEqual(result["cursor"]["y"], 200)

        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["reason"], "detected_linear_fallback_gaze_error")
        self.assertEqual(diagnostics["mapping_source"], "frame_linear_fallback")
        self.assertTrue(diagnostics["used_fallback"])
        self.assertIn("gaze_exception:", diagnostics.get("gaze_error", ""))
        map_mock.assert_not_called()

    def test_no_detection_uses_center_then_hold_last(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1200, 800))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            side_effect=[_track_miss(), _track_miss()],
        ):
            first = processor.process_frame(frame_bytes, {})
            second = processor.process_frame(frame_bytes, {})

        self.assertTrue(first["ok"])
        self.assertEqual(first["cursor"]["x"], 600)
        self.assertEqual(first["cursor"]["y"], 400)
        self.assertEqual(first["diagnostics"]["reason"], "no_detection_center")
        self.assertTrue(first["diagnostics"]["used_fallback"])

        self.assertTrue(second["ok"])
        self.assertEqual(second["cursor"]["x"], 600)
        self.assertEqual(second["cursor"]["y"], 400)
        self.assertEqual(second["diagnostics"]["reason"], "no_detection_hold_last")
        self.assertTrue(second["diagnostics"]["used_fallback"])

    def test_detection_smoothing_dampens_jump(self):
        """1€ filter must initialize on first sample, then dampen the next jump."""
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            side_effect=[_track_hit((10, 10)), _track_hit((20, 20))],
        ):
            first = processor.process_frame(frame_bytes, {})
            second = processor.process_frame(frame_bytes, {})

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(first["diagnostics"]["mapping_source"], "baseline_collecting")
        self.assertEqual(second["diagnostics"]["mapping_source"], "baseline_collecting")

        # first sample passes through unchanged
        self.assertEqual(first["diagnostics"]["smoothed_pupil_center"], {"x": 10, "y": 10})
        # second sample is between previous-smoothed and raw input — i.e. damped
        smoothed = second["diagnostics"]["smoothed_pupil_center"]
        smoothed_x = smoothed["x"]
        smoothed_y = smoothed["y"]
        self.assertGreaterEqual(smoothed_x, 10)
        self.assertLessEqual(smoothed_x, 20)
        self.assertGreaterEqual(smoothed_y, 10)
        self.assertLessEqual(smoothed_y, 20)

    def test_low_confidence_hold_keeps_last_smoothed_pupil(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            side_effect=[
                _track_hit((100, 50), confidence=0.85),
                _track_hit((104, 52), confidence=0.20, source="hold"),
            ],
        ):
            first = processor.process_frame(frame_bytes, {})
            second = processor.process_frame(frame_bytes, {})

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["diagnostics"]["tracker_source"], "hold")
        self.assertEqual(second["diagnostics"]["raw_pupil_center"], {"x": 104, "y": 52})
        self.assertEqual(second["diagnostics"]["smoothed_pupil_center"], {"x": 100, "y": 50})
        self.assertEqual(second["diagnostics"]["baseline_sample_count"], 1)
        self.assertEqual(second["diagnostics"]["mapping_source"], "baseline_collecting")

    def test_baseline_collects_only_confident_non_hold_samples(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        processor._baseline_required_samples = 2
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            side_effect=[
                _track_hit((100, 50), confidence=0.85, source="full"),
                _track_hit((105, 52), confidence=0.20, source="hold"),
                _track_hit((90, 45), confidence=0.20, source="full"),
                _track_hit((102, 51), confidence=0.85, source="window"),
            ],
        ):
            first = processor.process_frame(frame_bytes, {})
            second = processor.process_frame(frame_bytes, {})
            third = processor.process_frame(frame_bytes, {})
            fourth = processor.process_frame(frame_bytes, {})

        self.assertEqual(first["diagnostics"]["baseline_sample_count"], 1)
        self.assertEqual(second["diagnostics"]["baseline_sample_count"], 1)
        self.assertEqual(third["diagnostics"]["baseline_sample_count"], 1)
        self.assertEqual(fourth["diagnostics"]["baseline_sample_count"], 2)
        self.assertTrue(fourth["diagnostics"]["baseline_ready"])
        self.assertEqual(fourth["diagnostics"]["baseline_pupil_center"], {"x": 101.0, "y": 50.5})

    def test_baseline_median_is_established_after_required_samples(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        processor._baseline_required_samples = 3
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            side_effect=[
                _track_hit((90, 45)),
                _track_hit((110, 55)),
                _track_hit((100, 50)),
            ],
        ):
            processor.process_frame(frame_bytes, {})
            processor.process_frame(frame_bytes, {})
            result = processor.process_frame(frame_bytes, {})

        self.assertTrue(result["diagnostics"]["baseline_ready"])
        self.assertEqual(result["diagnostics"]["baseline_sample_count"], 3)
        self.assertEqual(result["diagnostics"]["baseline_pupil_center"], {"x": 100.0, "y": 50.0})

    def test_neutral_baseline_maps_to_screen_center(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        _ready_baseline(processor, center=(100, 50))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            return_value=_track_hit((100, 50)),
        ):
            result = processor.process_frame(frame_bytes, {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["cursor"]["x"], 500)
        self.assertEqual(result["cursor"]["y"], 250)
        self.assertEqual(result["diagnostics"]["mapping_source"], "neutral_baseline")
        self.assertEqual(result["diagnostics"]["reason"], "detected_baseline_mapped")
        self.assertEqual(result["diagnostics"]["baseline_offset"], {"x": 0.0, "y": 0.0})

    def test_baseline_offsets_map_symmetrically(self):
        frame_bytes = _jpeg_frame(width=200, height=100)
        right_processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        left_processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        _ready_baseline(right_processor, center=(100, 50))
        _ready_baseline(left_processor, center=(100, 50))

        with patch.object(
            right_processor._pupil_tracker,
            "update",
            return_value=_track_hit((110, 50)),
        ):
            right = right_processor.process_frame(frame_bytes, {})

        with patch.object(
            left_processor._pupil_tracker,
            "update",
            return_value=_track_hit((90, 50)),
        ):
            left = left_processor.process_frame(frame_bytes, {})

        self.assertEqual(right["diagnostics"]["mapping_source"], "neutral_baseline")
        self.assertEqual(left["diagnostics"]["mapping_source"], "neutral_baseline")
        self.assertEqual(right["cursor"]["x"] - 500, 500 - left["cursor"]["x"])
        self.assertEqual(right["cursor"]["y"], 250)
        self.assertEqual(left["cursor"]["y"], 250)

    def test_baseline_deadzone_suppresses_tiny_offsets(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        _ready_baseline(processor, center=(100, 50))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            return_value=_track_hit((101, 50)),
        ):
            result = processor.process_frame(frame_bytes, {})

        self.assertEqual(result["cursor"]["x"], 500)
        self.assertEqual(result["cursor"]["y"], 250)
        self.assertEqual(result["diagnostics"]["baseline_offset"], {"x": 0.0, "y": 0.0})

    def test_baseline_mapping_clamps_to_screen_bounds(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        _ready_baseline(processor, center=(100, 50))
        processor._baseline_gain_x = 100.0
        processor._baseline_gain_y = 100.0
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            return_value=_track_hit((199, 99)),
        ):
            result = processor.process_frame(frame_bytes, {})

        self.assertEqual(result["cursor"]["x"], 999)
        self.assertEqual(result["cursor"]["y"], 499)
        self.assertEqual(result["diagnostics"]["mapping_source"], "neutral_baseline")

    def test_gaze_projection_fallback_still_works_when_baseline_mapper_cannot_map(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        _ready_baseline(processor, center=(100, 50))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            return_value=_track_hit((100, 50)),
        ), patch.object(
            processor,
            "_map_with_baseline",
            return_value=None,
        ), patch.object(
            processor._gaze_tracker,
            "extract_gaze_numbers",
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

        self.assertEqual(result["cursor"]["x"], 111)
        self.assertEqual(result["cursor"]["y"], 222)
        self.assertEqual(result["diagnostics"]["mapping_source"], "gaze_angles_cursorcontroller")
        self.assertEqual(result["diagnostics"]["single_angles"], [8.0, -2.0])
        gaze_mock.assert_called_once()
        map_mock.assert_called_once_with(
            angle_h=8.0,
            angle_v=-2.0,
            screen_width=1000,
            screen_height=500,
        )

    def test_full_miss_resets_smoothed_pupil(self):
        processor = ContourPupilFrameProcessor(screen_size_provider=lambda: (1000, 500))
        frame_bytes = _jpeg_frame(width=200, height=100)

        with patch.object(
            processor._pupil_tracker,
            "update",
            side_effect=[_track_hit((100, 50), confidence=0.85), _track_miss()],
        ), patch.object(
            processor._gaze_tracker,
            "extract_gaze_numbers",
            return_value={
                "single_gaze_vector": [0.1, 0.2, 0.9],
                "single_angles": [8.0, -2.0],
                "single_offset": [0.05, -0.02],
            },
        ), patch(
            "app.services.contour_pupil_processor.map_gaze_angles_to_screen",
            return_value=(111, 222),
        ):
            first = processor.process_frame(frame_bytes, {})
            second = processor.process_frame(frame_bytes, {})

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertIsNone(processor._smoothed_pupil_center)
        self.assertEqual(second["diagnostics"]["tracker_source"], "miss")
        self.assertEqual(second["diagnostics"]["reason"], "no_detection_hold_last")


if __name__ == "__main__":
    unittest.main()
