import unittest
from unittest.mock import patch

from app.services.pipeline_controller import PipelineController


class _FakeSerialContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def reset_input_buffer(self):
        return None


class PipelineControllerHandshakeTests(unittest.TestCase):
    def test_provision_wifi_retries_then_succeeds(self):
        controller = PipelineController()
        fake_serial = _FakeSerialContext()
        responses = iter(
            [
                (False, None, None, "n-1"),
                (False, "192.168.1.120", None, "n-2"),
            ]
        )

        with patch("app.services.pipeline_controller.BYPASS_SERIAL", False), patch(
            "app.services.pipeline_controller.SERIAL_HANDSHAKE_ATTEMPTS", 3
        ), patch(
            "app.services.pipeline_controller.SERIAL_HANDSHAKE_ATTEMPT_TIMEOUT_S", 0.01
        ), patch(
            "app.services.pipeline_controller.serial_connect.open_serial",
            return_value=fake_serial,
        ), patch.object(
            controller,
            "_run_serial_handshake_attempt",
            side_effect=lambda *_args, **_kwargs: next(responses),
        ):
            ip_addr = controller._provision_wifi(
                ssid="MyWifi",
                password="pw",
                serial_port="/dev/tty.usbmodem",
                baud=115200,
            )

        self.assertEqual(ip_addr, "192.168.1.120")
        state = controller.get_state()
        self.assertEqual(state["phase"], "wifi_connected")
        self.assertEqual(state["esp32_ip"], "192.168.1.120")

    def test_provision_wifi_raises_on_device_error(self):
        controller = PipelineController()
        fake_serial = _FakeSerialContext()

        with patch("app.services.pipeline_controller.BYPASS_SERIAL", False), patch(
            "app.services.pipeline_controller.SERIAL_HANDSHAKE_ATTEMPTS", 3
        ), patch(
            "app.services.pipeline_controller.serial_connect.open_serial",
            return_value=fake_serial,
        ), patch.object(
            controller,
            "_run_serial_handshake_attempt",
            return_value=(True, None, "WIFI bad_password", "n-1"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                controller._provision_wifi(
                    ssid="MyWifi",
                    password="bad",
                    serial_port="/dev/tty.usbmodem",
                    baud=115200,
                )

        self.assertIn("ESP32 reported error: WIFI bad_password", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
