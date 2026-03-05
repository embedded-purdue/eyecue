from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.pipeline_controller import PipelineController


class _FakeSerial:
    def __init__(self, lines):
        self._lines = [f"{line}\n".encode("utf-8") for line in lines]

    def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class PipelineControllerTest(unittest.TestCase):
    def test_ack_and_ip_same_line(self) -> None:
        controller = PipelineController()
        ser = _FakeSerial(["OK 192.168.1.10"])
        saw_ok, ip_addr = controller._wait_for_ack_and_ip(ser, timeout_s=0.1)
        self.assertTrue(saw_ok)
        self.assertEqual(ip_addr, "192.168.1.10")

    def test_ack_then_ip_line(self) -> None:
        controller = PipelineController()
        ser = _FakeSerial(["booting", "OK", "IP address: 10.0.0.7"])
        saw_ok, ip_addr = controller._wait_for_ack_and_ip(ser, timeout_s=0.1)
        self.assertTrue(saw_ok)
        self.assertEqual(ip_addr, "10.0.0.7")

    def test_connect_sets_state_and_alert(self) -> None:
        controller = PipelineController()
        with patch.object(controller, "_run_pipeline", return_value=None):
            state = controller.connect(ssid="TestNet", password="pw", serial_port="/dev/ttyUSB0")

        self.assertEqual(state["phase"], "connecting_esp32")
        self.assertEqual(state["ssid"], "TestNet")
        self.assertEqual(state["serial_port"], "/dev/ttyUSB0")
        self.assertFalse(state["tracking_enabled"])
        self.assertGreaterEqual(len(state["alerts"]), 1)
        self.assertEqual(state["alerts"][-1]["message"], "Connecting to ESP32…")

        controller.stop()

    def test_tracking_toggle(self) -> None:
        controller = PipelineController()
        state = controller.set_tracking(True)
        self.assertTrue(state["tracking_enabled"])
        state = controller.set_tracking(False)
        self.assertFalse(state["tracking_enabled"])


if __name__ == "__main__":
    unittest.main()

