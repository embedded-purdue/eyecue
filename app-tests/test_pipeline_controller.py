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
                (False, None, None, "n-1", ["READY pico"]),
                (False, "192.168.1.120", None, "n-2", ["OK 192.168.1.120"]),
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
            return_value=(True, None, "WIFI bad_password", "n-1", ["ERR WIFI bad_password"]),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                controller._provision_wifi(
                    ssid="MyWifi",
                    password="bad",
                    serial_port="/dev/tty.usbmodem",
                    baud=115200,
                )

        self.assertIn("ESP32 reported error: WIFI bad_password", str(ctx.exception))

    def test_provision_wifi_debug_logging_adds_tx_rx_alerts(self):
        controller = PipelineController()
        fake_serial = _FakeSerialContext()

        def _fake_read(*_args, **kwargs):
            line_logger = kwargs.get("line_logger")
            if line_logger:
                line_logger("READY pico-w line-json receiver")
                line_logger("ACK WIFI_CONFIG nonce-1")
                line_logger("OK 192.168.1.120")
            return True, "192.168.1.120", None, [
                "READY pico-w line-json receiver",
                "ACK WIFI_CONFIG nonce-1",
                "OK 192.168.1.120",
            ]

        with patch("app.services.pipeline_controller.BYPASS_SERIAL", False), patch(
            "app.services.pipeline_controller.SERIAL_DEBUG", True
        ), patch(
            "app.services.pipeline_controller.SERIAL_HANDSHAKE_ATTEMPTS", 1
        ), patch(
            "app.services.pipeline_controller.serial_connect.open_serial",
            return_value=fake_serial,
        ), patch(
            "app.services.pipeline_controller.serial_connect.make_nonce",
            return_value="nonce-1",
        ), patch(
            "app.services.pipeline_controller.serial_connect.send_wifi_config_command",
            return_value='WIFI_CONFIG {"ssid":"MyWifi","password":"pw","nonce":"nonce-1"}',
        ), patch(
            "app.services.pipeline_controller.serial_connect.read_handshake_signals",
            side_effect=_fake_read,
        ):
            controller._provision_wifi(
                ssid="MyWifi",
                password="pw",
                serial_port="/dev/tty.usbmodem",
                baud=115200,
            )

        messages = [alert["message"] for alert in controller.get_state()["alerts"]]
        self.assertTrue(any(msg.startswith("SERIAL TX ack_attempt=1/") for msg in messages))
        self.assertIn("SERIAL RX READY pico-w line-json receiver", messages)
        self.assertIn("SERIAL RX ACK WIFI_CONFIG nonce-1", messages)
        self.assertIn("SERIAL RX OK 192.168.1.120", messages)

    def test_run_serial_handshake_attempt_retries_for_ack_then_waits_for_ok(self):
        controller = PipelineController()

        read_responses = [
            (False, None, None, ["noise-before-ack"]),
            (True, None, None, ["ACK WIFI_CONFIG nonce-42"]),
            (False, "192.168.1.42", None, ["OK 192.168.1.42"]),
        ]

        with patch("app.services.pipeline_controller.SERIAL_ACK_RETRIES", 3), patch(
            "app.services.pipeline_controller.SERIAL_ACK_TIMEOUT_S", 0.01
        ), patch(
            "app.services.pipeline_controller.serial_connect.make_nonce", return_value="nonce-42"
        ), patch(
            "app.services.pipeline_controller.serial_connect.send_wifi_config_command",
            return_value='WIFI_CONFIG {"ssid":"MyWifi","password":"pw","nonce":"nonce-42"}',
        ) as send_mock, patch(
            "app.services.pipeline_controller.serial_connect.read_handshake_signals",
            side_effect=read_responses,
        ) as read_mock:
            saw_ack, ip_addr, device_error, nonce, lines = controller._run_serial_handshake_attempt(
                object(),
                ssid="MyWifi",
                password="pw",
                timeout_s=5.0,
            )

        self.assertTrue(saw_ack)
        self.assertEqual(ip_addr, "192.168.1.42")
        self.assertIsNone(device_error)
        self.assertEqual(nonce, "nonce-42")
        self.assertEqual(lines, ["noise-before-ack", "ACK WIFI_CONFIG nonce-42", "OK 192.168.1.42"])
        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual(read_mock.call_count, 3)

    def test_run_serial_handshake_attempt_returns_no_ack_after_quick_retries(self):
        controller = PipelineController()

        with patch("app.services.pipeline_controller.SERIAL_ACK_RETRIES", 2), patch(
            "app.services.pipeline_controller.SERIAL_ACK_TIMEOUT_S", 0.01
        ), patch(
            "app.services.pipeline_controller.serial_connect.make_nonce", return_value="nonce-77"
        ), patch(
            "app.services.pipeline_controller.serial_connect.send_wifi_config_command",
            return_value='WIFI_CONFIG {"ssid":"MyWifi","password":"pw","nonce":"nonce-77"}',
        ) as send_mock, patch(
            "app.services.pipeline_controller.serial_connect.read_handshake_signals",
            side_effect=[
                (False, None, None, ["READY pico"]),
                (False, None, None, ["still waiting"]),
            ],
        ) as read_mock:
            saw_ack, ip_addr, device_error, nonce, lines = controller._run_serial_handshake_attempt(
                object(),
                ssid="MyWifi",
                password="pw",
                timeout_s=5.0,
            )

        self.assertFalse(saw_ack)
        self.assertIsNone(ip_addr)
        self.assertIsNone(device_error)
        self.assertEqual(nonce, "nonce-77")
        self.assertEqual(lines, ["READY pico", "still waiting"])
        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual(read_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
