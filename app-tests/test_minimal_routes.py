import unittest
from unittest.mock import patch

try:
    from app.app import create_app
    _CREATE_APP_IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - local env guard
    create_app = None
    _CREATE_APP_IMPORT_ERROR = exc


class _Port:
    def __init__(self, device, description="", hwid=""):
        self.device = device
        self.description = description
        self.hwid = hwid


class MinimalRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if create_app is None:
            raise unittest.SkipTest(f"Flask not available: {_CREATE_APP_IMPORT_ERROR}")

    def setUp(self):
        self.client = create_app().test_client()

    def test_health_route(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})

    @patch("app.routes.app_state.pipeline_controller.get_state")
    @patch("app.routes.app_state.serial_connect.list_serial_ports")
    @patch("app.routes.app_state.load_prefs")
    def test_bootstrap_contract(self, load_prefs_mock, list_ports_mock, get_state_mock):
        load_prefs_mock.return_value = {
            "wifi_ssid": "Velocity Wi-Fi",
            "wifi_password": "secret",
            "last_serial_port": "/dev/tty.usbmodem101",
        }
        list_ports_mock.return_value = [
            _Port("/dev/tty.usbmodem101", "Pico W", "USB VID:PID=2E8A:0005")
        ]
        get_state_mock.return_value = {
            "phase": "idle",
            "tracking_enabled": False,
            "alerts": [],
        }

        response = self.client.get("/app/bootstrap")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["data"]

        self.assertEqual(payload["prefs"]["wifi_ssid"], "Velocity Wi-Fi")
        self.assertEqual(payload["prefs"]["wifi_password"], "secret")
        self.assertEqual(payload["prefs"]["last_serial_port"], "/dev/tty.usbmodem101")
        self.assertEqual(payload["serial_ports"][0]["device"], "/dev/tty.usbmodem101")
        self.assertEqual(payload["runtime"]["phase"], "idle")
        self.assertFalse(payload["tracking_enabled"])

    @patch("app.routes.runtime.save_prefs")
    @patch("app.routes.runtime.load_prefs")
    @patch("app.routes.runtime.pipeline_controller.connect")
    def test_runtime_connect_persists_minimal_prefs(self, connect_mock, load_prefs_mock, save_prefs_mock):
        load_prefs_mock.return_value = {}
        connect_mock.return_value = {
            "phase": "connecting_esp32",
            "tracking_enabled": False,
            "alerts": [],
        }

        response = self.client.post(
            "/runtime/connect",
            json={
                "ssid": "Velocity Wi-Fi",
                "password": "secret",
                "serial_port": "/dev/tty.usbmodem101",
                "baud": 115200,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        connect_mock.assert_called_once()
        save_prefs_mock.assert_called_once_with(
            {
                "wifi_ssid": "Velocity Wi-Fi",
                "wifi_password": "secret",
                "last_serial_port": "/dev/tty.usbmodem101",
            }
        )

    def test_runtime_connect_requires_serial_port(self):
        response = self.client.post(
            "/runtime/connect",
            json={"ssid": "Velocity Wi-Fi", "password": "secret"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("serial_port is required", response.get_json()["error"])

    @patch("app.routes.runtime.save_prefs")
    @patch("app.routes.runtime.load_prefs")
    @patch("app.routes.runtime.pipeline_controller.connect")
    def test_runtime_bypass_allows_missing_fields(self, connect_mock, load_prefs_mock, save_prefs_mock):
        load_prefs_mock.return_value = {"wifi_ssid": "old", "wifi_password": "old", "last_serial_port": "old"}
        connect_mock.return_value = {
            "phase": "bypass_mode",
            "tracking_enabled": False,
            "alerts": [],
        }

        response = self.client.post("/runtime/bypass", json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        connect_mock.assert_called_once_with(
            ssid="",
            password="",
            serial_port="",
            baud=115200,
            bypass=True,
        )
        save_prefs_mock.assert_called_once_with(
            {"wifi_ssid": "old", "wifi_password": "old", "last_serial_port": "old"}
        )

    @patch("app.routes.runtime.save_prefs")
    @patch("app.routes.runtime.load_prefs")
    @patch("app.routes.runtime.pipeline_controller.connect")
    def test_runtime_bypass_updates_prefs_when_fields_provided(self, connect_mock, load_prefs_mock, save_prefs_mock):
        load_prefs_mock.return_value = {}
        connect_mock.return_value = {
            "phase": "bypass_mode",
            "tracking_enabled": False,
            "alerts": [],
        }

        response = self.client.post(
            "/runtime/bypass",
            json={
                "ssid": "Velocity Wi-Fi",
                "password": "secret",
                "serial_port": "/dev/tty.usbmodem101",
            },
        )
        self.assertEqual(response.status_code, 200)
        save_prefs_mock.assert_called_once_with(
            {
                "wifi_ssid": "Velocity Wi-Fi",
                "wifi_password": "secret",
                "last_serial_port": "/dev/tty.usbmodem101",
            }
        )

    @patch("app.routes.runtime.pipeline_controller.set_tracking")
    def test_runtime_tracking_toggle(self, set_tracking_mock):
        set_tracking_mock.return_value = {
            "phase": "idle",
            "tracking_enabled": True,
            "alerts": [],
        }
        response = self.client.post("/runtime/tracking", json={"enabled": True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        set_tracking_mock.assert_called_once_with(True)

    def test_calibration_routes_removed(self):
        requests = [
            ("get", "/runtime/calibrate/state"),
            ("post", "/runtime/calibrate/start"),
            ("post", "/runtime/calibrate/record"),
            ("post", "/runtime/calibrate/finish"),
            ("post", "/runtime/calibrate/cancel"),
            ("post", "/runtime/calibrate/quick"),
            ("get", "/runtime/gaze/current"),
        ]

        for method, path in requests:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, json={})
                self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
