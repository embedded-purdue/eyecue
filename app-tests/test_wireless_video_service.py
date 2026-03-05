from __future__ import annotations

import unittest

from app.services.runtime_store import RuntimeStore
from app.services.wireless_video_service import WirelessVideoService


class CursorProcessor:
    def process_frame(self, frame_bytes: bytes, metadata):
        return {
            "ok": True,
            "cursor": {"x": 101, "y": 202, "confidence": 0.9},
            "diagnostics": {"stage": "test", "reason": "cursor_override"},
            "error": None,
        }


class FailingProcessor:
    def process_frame(self, frame_bytes: bytes, metadata):
        return {
            "ok": False,
            "cursor": None,
            "diagnostics": {"stage": "test", "reason": "forced_failure"},
            "error": "forced failure",
        }


class FallbackCursorProcessor:
    def process_frame(self, frame_bytes: bytes, metadata):
        return {
            "ok": True,
            "cursor": {"x": 111, "y": 222, "confidence": 0.1},
            "diagnostics": {"stage": "test", "reason": "fallback", "detection_ok": False, "used_fallback": True},
            "error": None,
        }


class WirelessVideoServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_store = RuntimeStore()
        self.service = WirelessVideoService(self.runtime_store, frame_buffer_max=3)

    def test_ring_buffer_bounds(self) -> None:
        for i in range(5):
            self.service.run_frame_pipeline(
                frame_bytes=f"frame-{i}".encode("utf-8"),
                metadata={"seq": i, "frame_ts_ms": 1700000000000 + i},
            )

        snapshot = self.service.get_debug_snapshot()
        self.assertEqual(len(snapshot["frames"]), 3)
        self.assertEqual(snapshot["frames"][0]["seq"], 2)

        video_state = self.runtime_store.get_wireless_video_snapshot()
        self.assertEqual(video_state["frames_received"], 5)
        self.assertEqual(video_state["frames_processed"], 5)
        self.assertGreaterEqual(video_state["frames_dropped"], 2)

    def test_stub_processor_diagnostics(self) -> None:
        self.service.run_frame_pipeline(frame_bytes=b"jpeg-bytes", metadata={"seq": 1})
        result = self.service.get_debug_snapshot()["results"][-1]

        self.assertTrue(result["ok"])
        self.assertFalse(result["cursor_published"])
        self.assertEqual(result["diagnostics"]["reason"], "not_implemented")

    def test_cursor_publish_path(self) -> None:
        self.service.set_processor(CursorProcessor())
        self.service.run_frame_pipeline(frame_bytes=b"jpeg-bytes", metadata={"seq": 9, "frame_ts_ms": 1710000000000})

        state = self.runtime_store.get_state()
        self.assertIsNotNone(state["cursor"]["last_sample"])
        self.assertEqual(state["cursor"]["last_sample"]["source"], "wireless")
        self.assertEqual(state["cursor"]["last_sample"]["x"], 101.0)

        result = self.service.get_debug_snapshot()["results"][-1]
        self.assertTrue(result["cursor_published"])

    def test_invalid_frame_bytes_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.service.run_frame_pipeline(frame_bytes=b"", metadata={})

    def test_processing_error_recorded(self) -> None:
        self.service.set_processor(FailingProcessor())
        self.service.run_frame_pipeline(frame_bytes=b"jpeg-bytes", metadata={"seq": 7})

        video_state = self.runtime_store.get_wireless_video_snapshot()
        self.assertEqual(video_state["last_processing_error"], "forced failure")

    def test_fallback_count_increments(self) -> None:
        self.service.set_processor(FallbackCursorProcessor())
        self.service.run_frame_pipeline(frame_bytes=b"jpeg-bytes", metadata={"seq": 3})

        video_state = self.runtime_store.get_wireless_video_snapshot()
        self.assertEqual(video_state["fallback_count"], 1)
        self.assertFalse(video_state["last_detection_ok"])

    def test_processor_unavailable_raises(self) -> None:
        self.service.set_processor_availability(ready=False, error="missing cv deps", processor_name="contour_pupil")
        with self.assertRaises(RuntimeError):
            self.service.run_frame_pipeline(frame_bytes=b"jpeg-bytes", metadata={"seq": 1})


if __name__ == "__main__":
    unittest.main()
