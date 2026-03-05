from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    from app.app import create_app
    from app.prefs_utils import load_prefs, save_prefs
    from app.services.runtime_context import pipeline_controller

    RUNTIME_DEPS_AVAILABLE = True
except ModuleNotFoundError:
    RUNTIME_DEPS_AVAILABLE = False
    create_app = None
    load_prefs = None
    save_prefs = None
    pipeline_controller = None


@unittest.skipUnless(RUNTIME_DEPS_AVAILABLE, "flask runtime dependencies are required")
class MinimalRouteContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["EYE_PREFS_PATH"] = os.path.join(self._tmp.name, "prefs.json")
        save_prefs({"wifi_ssid": "SavedNet", "wifi_password": "SavedPass", "last_serial_port": "/dev/ttyS0"})

        self.app = create_app().test_client()
        pipeline_controller.stop()

    def tearDown(self) -> None:
        pipeline_controller.stop()
        os.environ.pop("EYE_PREFS_PATH", None)
        self._tmp.cleanup()

    def test_bootstrap_prefills_and_ports(self) -> None:
        fake_ports = [SimpleNamespace(device="/dev/ttyUSB0", description="USB Serial", hwid="abc123")]
        with patch("app.serial_connect.list_serial_ports", return_value=fake_ports):
            response = self.app.get("/app/bootstrap")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["prefs"]["wifi_ssid"], "SavedNet")
        self.assertEqual(data["prefs"]["wifi_password"], "SavedPass")
        self.assertEqual(data["prefs"]["last_serial_port"], "/dev/ttyS0")
        self.assertEqual(data["serial_ports"][0]["device"], "/dev/ttyUSB0")
        self.assertIn("runtime", data)
        self.assertIn("tracking_enabled", data)

    def test_runtime_connect_contract_and_prefs_save(self) -> None:
        mocked_state = {
            "phase": "connecting_esp32",
            "ssid": "MyNet",
            "serial_port": "/dev/ttyUSB0",
            "esp32_ip": None,
            "stream_url": None,
            "tracking_enabled": False,
            "frames_processed": 0,
            "last_frame_ts_ms": None,
            "last_error": None,
            "alerts": [],
        }
        with patch("app.routes.runtime.pipeline_controller.connect", return_value=mocked_state) as mocked_connect:
            response = self.app.post(
                "/runtime/connect",
                json={
                    "ssid": "MyNet",
                    "password": "MyPass",
                    "serial_port": "/dev/ttyUSB0",
                    "baud": 115200,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["phase"], "connecting_esp32")

        mocked_connect.assert_called_once_with(
            ssid="MyNet",
            password="MyPass",
            serial_port="/dev/ttyUSB0",
            baud=115200,
        )

        prefs = load_prefs()
        self.assertEqual(prefs["wifi_ssid"], "MyNet")
        self.assertEqual(prefs["wifi_password"], "MyPass")
        self.assertEqual(prefs["last_serial_port"], "/dev/ttyUSB0")

    def test_runtime_tracking_requires_enabled(self) -> None:
        response = self.app.post("/runtime/tracking", json={})
        self.assertEqual(response.status_code, 400)

    def test_serial_ports_contract(self) -> None:
        fake_ports = [SimpleNamespace(device="/dev/ttyUSB0", description="USB Serial", hwid="abc123")]
        with patch("app.serial_connect.list_serial_ports", return_value=fake_ports):
            response = self.app.get("/serial/ports")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"][0]["device"], "/dev/ttyUSB0")


if __name__ == "__main__":
    unittest.main()
